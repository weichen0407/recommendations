"""Batch runner for case JSON records."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .config import AppSettings, apply_env_file_to_process
from .nodes import (
    RuntimeDependencies,
    call_curl_task,
    check_user_token,
    finalize_result,
    refresh_user_token,
    route_after_token_check,
)
from .records import save_result_table
from .state import TopicWorkflowState

DEFAULT_CASE_RECORDS_CSV = "outputs/case_workflow_records.csv"
DEFAULT_CASE_RESULTS_JSON = "outputs/case_workflow_results.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read extracted case JSON records and generate Eureka links.",
    )
    parser.add_argument(
        "cases_json",
        nargs="?",
        default="cases/500articles.json",
        help="Path to a JSON array, or an object with an items/cases/records array.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum cases to process.")
    parser.add_argument("--offset", type=int, default=0, help="Number of cases to skip first.")
    parser.add_argument(
        "--records-csv",
        default=DEFAULT_CASE_RECORDS_CSV,
        help="CSV file used to append generated case records.",
    )
    parser.add_argument(
        "--records-md",
        default="",
        help="Optional Markdown table file regenerated from the CSV records.",
    )
    parser.add_argument(
        "--results-json",
        default=DEFAULT_CASE_RESULTS_JSON,
        help="JSON file updated after each processed case.",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="Command output format.",
    )
    parser.add_argument(
        "--wait-on-401",
        type=float,
        default=0.0,
        help="Seconds to wait after a 401 before checking whether auth changed.",
    )
    parser.add_argument(
        "--retry-on-auth-change",
        action="store_true",
        help="Retry the failed case if auth/signature/cookie changed after waiting.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=1,
        help="Maximum retry attempts per case after 401.",
    )
    parser.add_argument(
        "--import-clipboard-on-401",
        action="store_true",
        help="Poll the macOS clipboard during 401 waits and import a copied browser curl.",
    )
    parser.add_argument(
        "--auth-poll-interval",
        type=float,
        default=2.0,
        help="Seconds between auth-cache checks while waiting after 401.",
    )
    parser.add_argument(
        "--use-refresh",
        action="store_true",
        help="Allow refresh-token flow before curl. Disabled by default with --retry-on-auth-change.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    runtime = RuntimeDependencies(settings=settings)
    cases = load_case_items(args.cases_json, offset=args.offset, limit=args.limit)
    allow_refresh = args.use_refresh or not args.retry_on_auth_change

    if args.retry_on_auth_change and not allow_refresh:
        preflight = ensure_auth_ready(
            runtime=runtime,
            wait_on_401_seconds=args.wait_on_401,
            import_clipboard_on_401=args.import_clipboard_on_401,
            auth_poll_interval_seconds=args.auth_poll_interval,
            log_progress=args.output == "summary",
        )
        if not preflight["ready"]:
            raise SystemExit(_auth_preflight_error(preflight))

    results: list[dict[str, Any]] = []
    for case_index, item in cases:
        result = run_case_item(
            case_index=case_index,
            item=item,
            runtime=runtime,
            wait_on_401_seconds=args.wait_on_401,
            retry_on_auth_change=args.retry_on_auth_change,
            retry_attempts=args.retry_attempts,
            import_clipboard_on_401=args.import_clipboard_on_401,
            auth_poll_interval_seconds=args.auth_poll_interval,
            allow_refresh=allow_refresh,
            log_progress=args.output == "summary",
        )
        results.append(result)
        write_results_json(results=results, path=args.results_json)
        if not result_has_required_urls(result):
            raise SystemExit(url_generation_error(result, args.results_json))
        if result.get("row"):
            save_result_table(
                row=result["row"],
                csv_path=args.records_csv,
                markdown_path=args.records_md,
            )

    output = {
        "cases_json": args.cases_json,
        "processed": len(results),
        "success": sum(1 for item in results if item.get("curl_success")),
        "failed": sum(1 for item in results if not item.get("curl_success")),
        "records_csv": args.records_csv,
        "results_json": args.results_json,
        "results": results,
    }
    if args.records_md:
        output["records_md"] = args.records_md

    if args.output == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(output, ensure_ascii=False, indent=indent))
    else:
        print(build_summary(output))


def load_case_records(path: str) -> list[dict[str, Any]]:
    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"cases JSON not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"cases JSON must be valid JSON: {exc}") from exc

    return _records_from_payload(payload)


def load_case_items(path: str, offset: int = 0, limit: int = 3) -> list[tuple[int, dict[str, Any]]]:
    if limit < 1:
        raise SystemExit("--limit must be greater than 0")
    if offset < 0:
        raise SystemExit("--offset must be greater than or equal to 0")

    records = load_case_records(path)
    selected = records[offset : offset + limit]
    return [
        (case_index_from_item(item, offset + index), item)
        for index, item in enumerate(selected)
    ]


def case_index_from_item(item: dict[str, Any], fallback_index: int) -> int:
    value = item.get("case_index")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return fallback_index


def run_case_item(
    case_index: int,
    item: dict[str, Any],
    runtime: RuntimeDependencies,
    wait_on_401_seconds: float = 0.0,
    retry_on_auth_change: bool = False,
    retry_attempts: int = 1,
    import_clipboard_on_401: bool = False,
    auth_poll_interval_seconds: float = 2.0,
    allow_refresh: bool = True,
    log_progress: bool = False,
) -> dict[str, Any]:
    retry_events: list[dict[str, Any]] = []
    state = _run_case_once(
        case_index=case_index,
        item=item,
        runtime=runtime,
        allow_refresh=allow_refresh,
    )

    for attempt in range(max(0, retry_attempts)):
        if not _should_wait_and_retry(state, retry_on_auth_change, wait_on_401_seconds):
            break

        before_snapshot = _auth_snapshot(runtime)
        wait_result = _wait_for_auth_update(
            runtime=runtime,
            wait_seconds=wait_on_401_seconds,
            poll_interval_seconds=auth_poll_interval_seconds,
            import_clipboard=import_clipboard_on_401,
            case_index=case_index,
            attempt=attempt + 1,
            log_progress=log_progress,
        )
        after_snapshot = wait_result["snapshot"]
        auth_changed = before_snapshot != after_snapshot
        retry_events.append(
            {
                "attempt": attempt + 1,
                "wait_seconds": wait_on_401_seconds,
                "elapsed_seconds": wait_result["elapsed_seconds"],
                "auth_changed": auth_changed,
                "clipboard_imported": wait_result["clipboard_imported"],
            }
        )
        if not auth_changed:
            if log_progress:
                print(
                    f"[{case_index}] auth unchanged after {wait_result['elapsed_seconds']:.1f}s; "
                    "skip retry",
                    file=sys.stderr,
                    flush=True,
                )
            break

        if log_progress:
            print(
                f"[{case_index}] auth changed; retry current case",
                file=sys.stderr,
                flush=True,
            )
        state = _run_case_once(
            case_index=case_index,
            item=item,
            runtime=runtime,
            allow_refresh=allow_refresh,
        )

    row = (state.get("result_table_rows") or [{}])[0]

    return {
        "case_index": case_index,
        "input": state.get("topic", ""),
        "title": state.get("title", ""),
        "generated_prompt": state.get("generated_prompt", ""),
        "session_url": state.get("session_link", ""),
        "share_url": state.get("share_link", ""),
        "session_id": state.get("session_id", ""),
        "share_id": state.get("share_id", ""),
        "curl_success": state.get("curl_success", False),
        "curl_skipped": state.get("curl_skipped", False),
        "eureka_auth_status": state.get("eureka_auth_status", ""),
        "token_status": state.get("token_status", ""),
        "token_reason": state.get("token_reason", ""),
        "retry_count": len([event for event in retry_events if event.get("auth_changed")]),
        "retry_events": retry_events,
        "errors": state.get("errors", []),
        "row": row,
    }


def ensure_auth_ready(
    runtime: RuntimeDependencies,
    wait_on_401_seconds: float = 0.0,
    import_clipboard_on_401: bool = False,
    auth_poll_interval_seconds: float = 2.0,
    log_progress: bool = False,
) -> dict[str, Any]:
    state: TopicWorkflowState = {"errors": [], "debug": {}}
    state.update(check_user_token(state, runtime))
    if _token_is_ready_for_curl(state, runtime):
        return _auth_ready_result(state, waited=False)

    if wait_on_401_seconds > 0:
        before_snapshot = _auth_snapshot(runtime)
        wait_result = _wait_for_auth_update(
            runtime=runtime,
            wait_seconds=wait_on_401_seconds,
            poll_interval_seconds=auth_poll_interval_seconds,
            import_clipboard=import_clipboard_on_401,
            case_index="preflight",
            attempt=1,
            log_progress=log_progress,
        )
        after_snapshot = wait_result["snapshot"]
        state = {"errors": [], "debug": {}}
        state.update(check_user_token(state, runtime))
        return {
            **_auth_ready_result(state, waited=True),
            "auth_changed": before_snapshot != after_snapshot,
            "elapsed_seconds": wait_result["elapsed_seconds"],
            "clipboard_imported": wait_result["clipboard_imported"],
        }

    return _auth_ready_result(state, waited=False)


def _run_case_once(
    case_index: int,
    item: dict[str, Any],
    runtime: RuntimeDependencies,
    allow_refresh: bool = True,
) -> TopicWorkflowState:
    state = case_state_from_item(item=item, case_index=case_index)
    state.update(check_user_token(state, runtime))
    if allow_refresh and route_after_token_check(state) == "refresh_user_token":
        state.update(refresh_user_token(state, runtime))
        state.update(check_user_token(state, runtime))

    if _token_is_ready_for_curl(state, runtime):
        state.update(call_curl_task(state, runtime))
    else:
        state.update(_auth_not_ready_result(state))
    state.update(finalize_result(state))
    return state


def case_state_from_item(item: dict[str, Any], case_index: int = 0) -> TopicWorkflowState:
    title = _string(item.get("title")) or f"case-{case_index + 1}"
    generated_prompt = _string(item.get("output"))
    return {
        "topic": title,
        "generated_prompt": generated_prompt,
        "title": title,
        "categories": _string_list(item.get("categories")),
        "keywords": _string_list(item.get("keywords")),
        "description": _string(item.get("description")),
        "role": _string(item.get("role")),
        "industry": _string(item.get("industry")),
        "jtbd": _string_list(item.get("jtbd")),
        "date": _string(item.get("date")),
        "sub_industry": _string_list(item.get("sub_industry")),
        "errors": [] if generated_prompt else ["case output is empty"],
        "debug": {
            "case_index": case_index,
            "case_runner": True,
            "prompt_from_case_output": bool(generated_prompt),
        },
    }


def write_results_json(results: list[dict[str, Any]], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def result_has_required_urls(result: dict[str, Any]) -> bool:
    return bool(result.get("curl_success") and result.get("session_url") and result.get("share_url"))


def url_generation_error(result: dict[str, Any], results_json: str = "") -> str:
    errors = result.get("errors") or []
    reason = errors[0] if errors else "session_url/share_url missing"
    title = result.get("title") or result.get("input") or "untitled"
    saved_message = f" Current failure saved to {results_json}." if results_json else ""
    return (
        f"[{result.get('case_index')}] stop before next case: Eureka URL was not generated "
        f"for {title}. Reason: {reason}.{saved_message}"
    )


def build_summary(output: dict[str, Any]) -> str:
    lines = [
        f"processed={output['processed']} success={output['success']} failed={output['failed']}",
        f"records_csv={output['records_csv']}",
        f"results_json={output['results_json']}",
    ]
    if output.get("records_md"):
        lines.insert(2, f"records_md={output['records_md']}")
    for item in output["results"]:
        status = "ok" if item.get("curl_success") else "failed"
        errors = item.get("errors") or []
        error_message = f" error={errors[0]}" if errors else ""
        wait_count = len(item.get("retry_events") or [])
        wait_message = f" waits={wait_count}" if wait_count else ""
        retry_message = f" retries={item.get('retry_count', 0)}" if item.get("retry_count") else ""
        lines.append(
            f"[{item['case_index']}] {status} {item.get('title', '')} "
            f"session={item.get('session_url', '')} share={item.get('share_url', '')}"
            f"{wait_message}{retry_message}{error_message}"
        )
    return "\n".join(lines)


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = []
        for key in ("items", "cases", "records", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
    else:
        records = []

    if not records:
        raise SystemExit("cases JSON must contain at least one record")
    if not all(isinstance(item, dict) for item in records):
        raise SystemExit("each case record must be a JSON object")
    return records


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _should_wait_and_retry(
    state: TopicWorkflowState,
    retry_on_auth_change: bool,
    wait_on_401_seconds: float,
) -> bool:
    return (
        retry_on_auth_change
        and wait_on_401_seconds > 0
        and (
            state.get("eureka_auth_status") in {"unauthorized", "needs_auth_update"}
            or state.get("token_status") != "ready"
        )
    )


def _auth_snapshot(runtime: RuntimeDependencies) -> dict[str, str]:
    return runtime.get_eureka_token_manager().read_cached_auth_snapshot()


def _auth_ready_result(state: TopicWorkflowState, waited: bool) -> dict[str, Any]:
    return {
        "ready": state.get("token_status") == "ready",
        "token_status": state.get("token_status", ""),
        "token_reason": state.get("token_reason", ""),
        "eureka_auth_status": state.get("eureka_auth_status", ""),
        "waited": waited,
    }


def _auth_preflight_error(preflight: dict[str, Any]) -> str:
    reason = preflight.get("token_reason") or "authorization is not ready"
    if preflight.get("waited"):
        elapsed = float(preflight.get("elapsed_seconds") or 0)
        return (
            "Eureka authorization is still not ready after "
            f"{elapsed:.1f}s; copy a fresh api/eureka/query/conversational curl and run "
            "`uv run eureka-token import-curl --clipboard`. "
            f"Reason: {reason}"
        )
    return (
        "Eureka authorization is not ready; copy a fresh api/eureka/query/conversational curl "
        "and run `uv run eureka-token import-curl --clipboard`. "
        f"Reason: {reason}"
    )


def _wait_for_auth_update(
    runtime: RuntimeDependencies,
    wait_seconds: float,
    poll_interval_seconds: float,
    import_clipboard: bool,
    case_index: int | str,
    attempt: int,
    log_progress: bool,
) -> dict[str, Any]:
    started_at = time.monotonic()
    deadline = started_at + max(0.0, wait_seconds)
    original_snapshot = _auth_snapshot(runtime)
    clipboard_imported = False

    if log_progress:
        action = "copy query/conversational curl now" if import_clipboard else "import new curl now"
        print(
            f"[{case_index}] auth not ready/401; waiting {wait_seconds:.1f}s "
            f"for auth update ({action}), attempt {attempt}",
            file=sys.stderr,
            flush=True,
        )

    while time.monotonic() < deadline:
        if import_clipboard and _try_import_clipboard(runtime):
            clipboard_imported = True

        snapshot = _auth_snapshot(runtime)
        if snapshot != original_snapshot:
            return {
                "snapshot": snapshot,
                "elapsed_seconds": time.monotonic() - started_at,
                "clipboard_imported": clipboard_imported,
            }

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(max(0.1, poll_interval_seconds), remaining))

    return {
        "snapshot": _auth_snapshot(runtime),
        "elapsed_seconds": time.monotonic() - started_at,
        "clipboard_imported": clipboard_imported,
    }


def _try_import_clipboard(runtime: RuntimeDependencies) -> bool:
    try:
        result = subprocess.run(["pbpaste"], check=False, capture_output=True, text=True)
    except OSError:
        return False
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        imported = runtime.get_eureka_token_manager().import_curl(result.stdout)
    except ValueError:
        return False
    return bool(imported.get("has_authorization") or imported.get("has_signature_id"))


def _token_is_ready_for_curl(state: TopicWorkflowState, runtime: RuntimeDependencies) -> bool:
    return state.get("token_status") == "ready" and runtime.get_eureka_client().has_authorization_header()


def _auth_not_ready_result(state: TopicWorkflowState) -> dict[str, Any]:
    errors = list(state.get("errors") or [])
    token_reason = state.get("token_reason") or "authorization is not ready"
    errors.append(
        "Eureka authorization is not ready; import a fresh browser curl with "
        f"`uv run eureka-token import-curl --clipboard`: {token_reason}"
    )
    return {
        "curl_success": False,
        "curl_skipped": True,
        "eureka_auth_status": "needs_auth_update",
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "curl_task": "skipped: authorization is not ready",
        },
    }


if __name__ == "__main__":
    main()
