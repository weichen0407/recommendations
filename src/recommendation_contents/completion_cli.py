"""Validate Eureka session completion from saved result or record files."""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .cases_cli import DEFAULT_CASE_RESULTS_JSON, write_results_json
from .completion import CompletionStatus, parse_completion_status
from .config import AppSettings, apply_env_file_to_process
from .nodes import (
    RuntimeDependencies,
    check_user_token,
    refresh_user_token,
    route_after_token_check,
)
from .services.eureka_curl import CurlResult, parse_json_body

COMPLETION_RECORD_FIELDS = ["isCompleted", "completionStatus", "completionError"]
LEGACY_COMPLETION_RECORD_FIELDS = ["isCompletion", "isComplete"]
DEFAULT_INDUSTRY_RECORDS_CSVS = [
    "outputs/industry_outlook_records_en.csv",
    "outputs/industry_outlook_records_html_en.csv",
]
SESSION_ID_RE = re.compile(r"sess_[A-Za-z0-9_-]+")
DEFAULT_COMPLETION_MAX_PAGES = 20


@dataclass(frozen=True)
class SessionCompletionUpdate:
    case_index: int | str
    title: str
    session_id: str
    session_url: str
    share_url: str
    status: str
    is_complete: bool
    error_message: str
    http_status_code: int
    return_code: int
    status_path: str = ""
    error_path: str = ""
    response_body: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate saved Eureka sessions by querying their events endpoint.",
    )
    parser.add_argument(
        "--results-json",
        default="",
        help=(
            "Optional JSON results file containing session_id values. "
            "If no target is provided, existing industry outlook records are scanned first; "
            f"otherwise {DEFAULT_CASE_RESULTS_JSON} is used when it exists."
        ),
    )
    parser.add_argument(
        "--records-csv",
        action="append",
        default=[],
        help="Records CSV to scan/update. Repeat this option for multiple files.",
    )
    parser.add_argument(
        "--usage-csv",
        action="append",
        default=[],
        help="Optional usage CSV to update by case_index/session_url. Repeat for multiple files.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum sessions to check.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_COMPLETION_MAX_PAGES,
        help="Maximum event pages to follow when has_more=true.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Recheck sessions already marked isCompleted=true.",
    )
    parser.add_argument(
        "--progress",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print per-session progress logs to stderr. Defaults to on for summary output.",
    )
    parser.add_argument(
        "--use-refresh",
        action="store_true",
        help="Allow refresh-token flow before querying session events.",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="Command output format.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    records_csvs = list(args.records_csv or [])
    results_json = args.results_json
    if not results_json and not records_csvs:
        records_csvs = [path for path in DEFAULT_INDUSTRY_RECORDS_CSVS if Path(path).exists()]
        if not records_csvs and Path(DEFAULT_CASE_RESULTS_JSON).exists():
            results_json = DEFAULT_CASE_RESULTS_JSON
    if not results_json and not records_csvs:
        raise SystemExit("pass at least one --records-csv or --results-json")

    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    runtime = RuntimeDependencies(settings=settings)
    _ensure_auth_ready(runtime, allow_refresh=args.use_refresh)
    log_progress = args.progress if args.progress is not None else args.output == "summary"

    updates: list[SessionCompletionUpdate] = []
    records_updated: dict[str, int] = {}
    results_checked = 0

    if results_json:
        results_path = Path(results_json)
        results = _load_results(results_path)
        result_updates = validate_results(
            results=results,
            runtime=runtime,
            limit=args.limit,
            recheck_completed=args.all,
            max_pages=args.max_pages,
            log_progress=log_progress,
        )
        write_results_json(results=results, path=str(results_path))
        results_checked = len(result_updates)
        updates.extend(result_updates)
        for records_csv in records_csvs:
            records_updated[records_csv] = update_records_csv(records_csv, result_updates)
    else:
        for records_csv in records_csvs:
            remaining = _remaining_limit(args.limit, len(updates))
            if remaining == 0:
                records_updated[records_csv] = 0
                continue
            record_updates = validate_records_csv(
                path=records_csv,
                runtime=runtime,
                limit=remaining,
                recheck_completed=args.all,
                max_pages=args.max_pages,
                log_progress=log_progress,
            )
            records_updated[records_csv] = len(record_updates)
            updates.extend(record_updates)

    usage_updated = {
        usage_csv: update_usage_csv(usage_csv, updates)
        for usage_csv in list(args.usage_csv or [])
    }

    output = {
        "results_json": results_json,
        "records_csv": records_csvs,
        "usage_csv": list(args.usage_csv or []),
        "checked": len(updates),
        "results_checked": results_checked,
        "records_updated": records_updated,
        "usage_updated": usage_updated,
        "status_counts": dict(Counter(update.status for update in updates)),
        "updates": [update.__dict__ for update in updates],
    }
    if args.output == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        print(_format_summary(output))


def validate_results(
    results: list[dict[str, Any]],
    runtime: RuntimeDependencies,
    limit: int = 0,
    recheck_completed: bool = False,
    max_pages: int = DEFAULT_COMPLETION_MAX_PAGES,
    log_progress: bool = False,
) -> list[SessionCompletionUpdate]:
    updates: list[SessionCompletionUpdate] = []
    client = runtime.get_eureka_client()
    if not client.has_completion_endpoint():
        raise SystemExit("EUREKA_COMPLETION_ENDPOINT is required to validate Eureka sessions")

    candidates = _result_completion_candidates(
        results=results,
        limit=limit,
        recheck_completed=recheck_completed,
    )
    total = len(candidates)
    for progress_index, result in enumerate(candidates, start=1):
        if not isinstance(result, dict):
            continue

        session_id = _result_session_id(result)
        if not session_id:
            continue

        _log_completion_progress(
            enabled=log_progress,
            progress_index=progress_index,
            total=total,
            target="results-json",
            result=result,
            session_id=session_id,
            phase="checking",
        )
        curl_result = _get_completion_status_until_final_page(client, session_id, max_pages=max_pages)
        update = _completion_update_from_response(
            result={**result, "session_id": session_id},
            curl_result=curl_result,
        )
        apply_completion_update(result, update)
        updates.append(update)
        _log_completion_progress(
            enabled=log_progress,
            progress_index=progress_index,
            total=total,
            target="results-json",
            update=update,
            phase="done",
            pages=_completion_page_count(curl_result),
        )
    return updates


def validate_records_csv(
    path: str,
    runtime: RuntimeDependencies,
    limit: int = 0,
    recheck_completed: bool = False,
    max_pages: int = DEFAULT_COMPLETION_MAX_PAGES,
    log_progress: bool = False,
) -> list[SessionCompletionUpdate]:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []

    client = runtime.get_eureka_client()
    if not client.has_completion_endpoint():
        raise SystemExit("EUREKA_COMPLETION_ENDPOINT is required to validate Eureka sessions")

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = _with_completion_fields(list(reader.fieldnames or []), after="share_url")
        rows = list(reader)

    candidates = _record_completion_candidates(
        rows=rows,
        limit=limit,
        recheck_completed=recheck_completed,
    )

    updates: list[SessionCompletionUpdate] = []
    total = len(candidates)
    for progress_index, (row_number, row) in enumerate(candidates, start=1):
        session_id = _session_id_from_row(row)
        if not session_id:
            update = _missing_session_update(row, row_number)
            _apply_completion_fields(row, update)
            updates.append(update)
            _log_completion_progress(
                enabled=log_progress,
                progress_index=progress_index,
                total=total,
                target=path,
                update=update,
                phase="done",
            )
            continue

        _log_completion_progress(
            enabled=log_progress,
            progress_index=progress_index,
            total=total,
            target=path,
            row=row,
            session_id=session_id,
            phase="checking",
        )
        curl_result = _get_completion_status_until_final_page(client, session_id, max_pages=max_pages)
        update = _completion_update_from_response(
            result=_result_from_record_row(row, row_number, session_id),
            curl_result=curl_result,
        )
        _apply_completion_fields(row, update)
        updates.append(update)
        _log_completion_progress(
            enabled=log_progress,
            progress_index=progress_index,
            total=total,
            target=path,
            update=update,
            phase="done",
            pages=_completion_page_count(curl_result),
        )

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return updates


def _result_completion_candidates(
    results: list[dict[str, Any]],
    limit: int,
    recheck_completed: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for result in results:
        if limit > 0 and len(candidates) >= limit:
            break
        if not isinstance(result, dict):
            continue
        if not recheck_completed and _result_is_complete(result):
            continue
        if not _result_session_id(result):
            continue
        candidates.append(result)
    return candidates


def _record_completion_candidates(
    rows: list[dict[str, Any]],
    limit: int,
    recheck_completed: bool,
) -> list[tuple[int, dict[str, Any]]]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row_number, row in enumerate(rows, start=1):
        _sync_completion_field(row)
        if limit > 0 and len(candidates) >= limit:
            break
        if not _string(row.get("session_url")):
            continue
        if not recheck_completed and _row_is_complete(row):
            continue
        candidates.append((row_number, row))
    return candidates


def _log_completion_progress(
    enabled: bool,
    progress_index: int,
    total: int,
    target: str,
    phase: str,
    session_id: str = "",
    result: dict[str, Any] | None = None,
    row: dict[str, Any] | None = None,
    update: SessionCompletionUpdate | None = None,
    pages: int = 0,
) -> None:
    if not enabled:
        return

    source = result or row or {}
    case_index = update.case_index if update else _string(source.get("case_index"))
    title = update.title if update else (_string(source.get("title")) or _string(source.get("input")))
    session = update.session_id if update else session_id

    parts = [
        f"[{progress_index}/{total}]",
        phase,
        f"target={_short_target(target)}",
    ]
    if case_index != "":
        parts.append(f"case_index={case_index}")
    if session:
        parts.append(f"session={session}")
    if title:
        parts.append(f"title={_short_log_value(title)}")
    if update:
        parts.append(f"status={update.status}")
        parts.append(f"isCompleted={str(update.is_complete).lower()}")
    if pages:
        parts.append(f"pages={pages}")
    if update and update.error_message:
        parts.append(f"error={_short_log_value(update.error_message, limit=140)}")

    print(" ".join(parts), file=sys.stderr, flush=True)


def _completion_page_count(curl_result: CurlResult) -> int:
    data = parse_json_body(curl_result.body)
    if isinstance(data, dict):
        pagination = data.get("pagination")
        if isinstance(pagination, dict):
            page_count = pagination.get("page_count")
            if isinstance(page_count, int):
                return page_count
            if isinstance(page_count, str) and page_count.isdigit():
                return int(page_count)
        pages = data.get("pages")
        if isinstance(pages, list):
            return len(pages)
    return 1 if curl_result.body else 0


def _short_target(target: str) -> str:
    if not target:
        return "unknown"
    if target == "results-json":
        return target
    return Path(target).name


def _short_log_value(value: Any, limit: int = 80) -> str:
    text = str(value).replace("\n", " ").strip()
    if len(text) <= limit:
        return json.dumps(text, ensure_ascii=False)
    return json.dumps(f"{text[: limit - 1]}…", ensure_ascii=False)


def apply_completion_update(result: dict[str, Any], update: SessionCompletionUpdate) -> None:
    result["completion_checked"] = True
    result["isCompleted"] = update.is_complete
    result.pop("isCompletion", None)
    result.pop("isComplete", None)
    result["completion_status"] = update.status
    result["completion_error"] = update.error_message
    result["completion_status_path"] = update.status_path
    result["completion_error_path"] = update.error_path
    result["eureka_completion_response"] = update.response_body
    result["eureka_completion_status_code"] = update.http_status_code
    result["eureka_completion_return_code"] = update.return_code

    errors = _without_completion_errors(result.get("errors") or [])
    if update.status == "failed":
        errors.append(
            f"Eureka session failed: {update.error_message}"
            if update.error_message
            else "Eureka session failed"
        )
    elif update.status == "http_error":
        errors.append(update.error_message)
    result["errors"] = errors

    row = result.get("row")
    if isinstance(row, dict):
        _apply_completion_fields(row, update)


def update_records_csv(path: str, updates: list[SessionCompletionUpdate]) -> int:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return 0

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = _with_completion_fields(list(reader.fieldnames or []), after="share_url")
        rows = list(reader)

    by_session_url = {update.session_url: update for update in updates if update.session_url}
    by_share_url = {update.share_url: update for update in updates if update.share_url}
    updated = 0
    for row in rows:
        _sync_completion_field(row)
        update = by_session_url.get(row.get("session_url", "")) or by_share_url.get(
            row.get("share_url", "")
        )
        if not update:
            continue
        _apply_completion_fields(row, update)
        updated += 1

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return updated


def update_usage_csv(path: str, updates: list[SessionCompletionUpdate]) -> int:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return 0

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = _with_completion_fields(list(reader.fieldnames or []), after="share_url")
        rows = list(reader)

    by_case_index = {str(update.case_index): update for update in updates}
    by_session_url = {update.session_url: update for update in updates if update.session_url}
    updated = 0
    for row in rows:
        _sync_completion_field(row)
        update = by_case_index.get(row.get("case_index", "")) or by_session_url.get(
            row.get("session_url", "")
        )
        if not update:
            continue
        _apply_completion_fields(row, update)
        if update.status == "completed":
            row["status"] = "used"
            row["error"] = ""
        elif update.status == "failed":
            row["status"] = "failed"
            row["error"] = update.error_message
        updated += 1

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return updated


def _ensure_auth_ready(runtime: RuntimeDependencies, allow_refresh: bool = False) -> None:
    state: dict[str, Any] = {"errors": [], "debug": {}}
    state.update(check_user_token(state, runtime))
    if allow_refresh and route_after_token_check(state) == "refresh_user_token":
        state.update(refresh_user_token(state, runtime))
        state.update(check_user_token(state, runtime))

    if not runtime.get_eureka_client().has_authorization_header():
        reason = state.get("token_reason") or "authorization is not ready"
        raise SystemExit(
            "Eureka authorization is not ready; import a fresh browser curl first. "
            f"Reason: {reason}"
        )


def _load_results(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"results JSON not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"results JSON must be valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit("results JSON must be a list")
    return data


def _completion_update_from_response(
    result: dict[str, Any],
    curl_result: CurlResult,
) -> SessionCompletionUpdate:
    if not curl_result.success:
        status = CompletionStatus(
            status="http_error",
            is_complete=False,
            error_message=_curl_error_message(curl_result),
        )
    else:
        status = parse_completion_status(parse_json_body(curl_result.body))

    return SessionCompletionUpdate(
        case_index=result.get("case_index", ""),
        title=_string(result.get("title")) or _string(result.get("input")),
        session_id=_string(result.get("session_id")),
        session_url=_string(result.get("session_url")),
        share_url=_string(result.get("share_url")),
        status=status.status,
        is_complete=status.is_complete,
        error_message=status.error_message,
        status_path=status.status_path,
        error_path=status.error_path,
        response_body=curl_result.body,
        http_status_code=curl_result.status_code,
        return_code=curl_result.return_code,
    )


def _missing_session_update(row: dict[str, Any], row_number: int) -> SessionCompletionUpdate:
    return SessionCompletionUpdate(
        case_index=_string(row.get("case_index")) or row_number,
        title=_string(row.get("title")) or _string(row.get("input")),
        session_id="",
        session_url=_string(row.get("session_url")),
        share_url=_string(row.get("share_url")),
        status="missing_session_id",
        is_complete=False,
        error_message="session_url does not contain a sess_ id",
        http_status_code=0,
        return_code=0,
    )


def _curl_error_message(curl_result: CurlResult) -> str:
    if curl_result.return_code != 0:
        return f"Eureka completion curl exited with code {curl_result.return_code}: {curl_result.stderr}"
    return f"Eureka completion returned HTTP {curl_result.status_code}"


def _get_completion_status_until_final_page(
    client: Any,
    session_id: str,
    max_pages: int = DEFAULT_COMPLETION_MAX_PAGES,
) -> CurlResult:
    max_pages = max(1, max_pages)
    pages: list[Any] = []
    page_results: list[CurlResult] = []
    seen_cursors: set[str] = set()
    cursor = ""

    for _page_number in range(max_pages):
        curl_result = _get_completion_status_page(client, session_id, cursor)
        page_results.append(curl_result)
        if not curl_result.success:
            return curl_result

        page_body = parse_json_body(curl_result.body)
        pages.append(page_body)
        if not _completion_has_more(page_body):
            return _combined_completion_result(page_results, pages)

        next_cursor = _completion_next_cursor(page_body)
        if not next_cursor:
            return _completion_pagination_error(
                page_results=page_results,
                pages=pages,
                message="Eureka completion returned has_more=true without stream_cursor",
            )
        if next_cursor in seen_cursors:
            return _completion_pagination_error(
                page_results=page_results,
                pages=pages,
                message=f"Eureka completion cursor repeated: {next_cursor}",
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return _completion_pagination_error(
        page_results=page_results,
        pages=pages,
        message=f"Eureka completion pagination exceeded --max-pages={max_pages}",
    )


def _get_completion_status_page(client: Any, session_id: str, cursor: str) -> CurlResult:
    if not cursor:
        return client.get_completion_status(session_id)
    if _completion_client_accepts_cursor(client):
        return client.get_completion_status(session_id, cursor=cursor)
    return CurlResult(
        payload={},
        body="",
        status_code=0,
        return_code=1,
        stderr="Eureka completion client does not support cursor pagination",
    )


def _completion_client_accepts_cursor(client: Any) -> bool:
    try:
        signature = inspect.signature(client.get_completion_status)
    except (TypeError, ValueError):
        return True
    return "cursor" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _completion_has_more(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    value = data.get("has_more", data.get("hasMore", False))
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _completion_next_cursor(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("stream_cursor", "streamCursor", "cursor", "next_cursor", "nextCursor"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _combined_completion_result(
    page_results: list[CurlResult],
    pages: list[Any],
) -> CurlResult:
    if len(page_results) == 1:
        return page_results[0]
    final_result = page_results[-1]
    combined_body = _combined_completion_body(pages)
    return CurlResult(
        payload=final_result.payload,
        body=json.dumps(combined_body, ensure_ascii=False),
        status_code=final_result.status_code,
        return_code=final_result.return_code,
        stderr=final_result.stderr,
    )


def _combined_completion_body(pages: list[Any]) -> Any:
    final_page = pages[-1] if pages else {}
    if not isinstance(final_page, dict):
        return {"pages": pages, "events": []}

    combined = dict(final_page)
    combined["events"] = _combined_events(pages)
    combined["pages"] = pages
    combined["pagination"] = {
        "page_count": len(pages),
        "final_has_more": _completion_has_more(final_page),
        "final_cursor": _completion_next_cursor(final_page),
    }
    return combined


def _combined_events(pages: list[Any]) -> list[Any]:
    events: list[Any] = []
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("events"), list):
            events.extend(page["events"])
    return events


def _completion_pagination_error(
    page_results: list[CurlResult],
    pages: list[Any],
    message: str,
) -> CurlResult:
    last_result = page_results[-1] if page_results else CurlResult(
        payload={},
        body="",
        status_code=0,
        return_code=1,
    )
    body = {
        "error": message,
        "pages": pages,
        "pagination": {
            "page_count": len(pages),
            "final_has_more": _completion_has_more(pages[-1]) if pages else False,
            "final_cursor": _completion_next_cursor(pages[-1]) if pages else "",
        },
    }
    return CurlResult(
        payload=last_result.payload,
        body=json.dumps(body, ensure_ascii=False),
        status_code=0,
        return_code=1,
        stderr=message,
    )


def _apply_completion_fields(row: dict[str, Any], update: SessionCompletionUpdate) -> None:
    value = "true" if update.is_complete else "false"
    row["isCompleted"] = value
    row.pop("isCompletion", None)
    row.pop("isComplete", None)
    row["completionStatus"] = update.status
    row["completionError"] = update.error_message


def _sync_completion_field(row: dict[str, Any]) -> None:
    value = _first_completion_value(row)
    if value:
        row["isCompleted"] = value
    row.pop("isCompletion", None)
    row.pop("isComplete", None)


def _with_completion_fields(fieldnames: list[str], after: str) -> list[str]:
    if not fieldnames:
        return fieldnames
    removable = set(COMPLETION_RECORD_FIELDS) | set(LEGACY_COMPLETION_RECORD_FIELDS)
    reordered = [field for field in fieldnames if field not in removable]
    anchor = "format" if after == "share_url" and "format" in reordered else after
    insert_at = reordered.index(anchor) + 1 if anchor in reordered else len(reordered)
    return reordered[:insert_at] + COMPLETION_RECORD_FIELDS + reordered[insert_at:]


def _result_is_complete(result: dict[str, Any]) -> bool:
    _sync_result_completion_field(result)
    return _completion_value_is_true(result.get("isCompleted"))


def _row_is_complete(row: dict[str, Any]) -> bool:
    return _completion_value_is_true(row.get("isCompleted"))


def _sync_result_completion_field(result: dict[str, Any]) -> None:
    value = _first_completion_value(result)
    if value:
        result["isCompleted"] = _completion_value_is_true(value)
    result.pop("isCompletion", None)
    result.pop("isComplete", None)
    row = result.get("row")
    if isinstance(row, dict):
        _sync_completion_field(row)


def _first_completion_value(row: dict[str, Any]) -> Any:
    for key in ("isCompleted", "isCompletion", "isComplete"):
        value = row.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _completion_value_is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _result_session_id(result: dict[str, Any]) -> str:
    return _string(result.get("session_id")) or _session_id_from_url(
        _string(result.get("session_url"))
    )


def _session_id_from_row(row: dict[str, Any]) -> str:
    return _string(row.get("session_id")) or _session_id_from_url(_string(row.get("session_url")))


def _session_id_from_url(value: str) -> str:
    if not value:
        return ""
    match = SESSION_ID_RE.search(unquote(value))
    return match.group(0) if match else ""


def _result_from_record_row(
    row: dict[str, Any],
    row_number: int,
    session_id: str,
) -> dict[str, Any]:
    return {
        "case_index": _string(row.get("case_index")) or row_number,
        "title": _string(row.get("title")) or _string(row.get("input")),
        "session_id": session_id,
        "session_url": _string(row.get("session_url")),
        "share_url": _string(row.get("share_url")),
    }


def _without_completion_errors(errors: list[Any]) -> list[str]:
    prefixes = (
        "Eureka session failed:",
        "Eureka completion returned",
        "Eureka completion curl exited",
        "Eureka completion did not finish",
    )
    return [
        str(error)
        for error in errors
        if isinstance(error, str) and not error.startswith(prefixes)
    ]


def _remaining_limit(limit: int, checked: int) -> int:
    if limit <= 0:
        return -1
    return max(0, limit - checked)


def _format_summary(output: dict[str, Any]) -> str:
    lines = [
        f"checked={output['checked']}",
        "records_updated=" + json.dumps(output["records_updated"], ensure_ascii=False),
        "usage_updated=" + json.dumps(output["usage_updated"], ensure_ascii=False),
        "status_counts=" + json.dumps(output["status_counts"], ensure_ascii=False),
    ]
    if output.get("results_json"):
        lines.insert(1, f"results_json={output['results_json']}")
    for item in output["updates"]:
        error = f" error={item['error_message']}" if item["error_message"] else ""
        lines.append(
            f"[{item['case_index']}] status={item['status']} "
            f"isCompleted={str(item['is_complete']).lower()} session={item['session_id']}{error}"
        )
    return "\n".join(lines)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


if __name__ == "__main__":
    main()
