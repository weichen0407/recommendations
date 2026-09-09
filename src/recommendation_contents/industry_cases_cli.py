"""Run unused case records by industry."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cases_cli import (
    DEFAULT_CASE_RECORDS_CSV,
    DEFAULT_CASE_RESULTS_JSON,
    build_summary,
    case_index_from_item,
    ensure_auth_ready,
    load_case_records,
    result_has_required_urls,
    run_case_item,
    url_generation_error,
    write_results_json,
)
from .config import AppSettings, apply_env_file_to_process
from .nodes import RuntimeDependencies
from .onboarding_fields import (
    onboarding_industry_value,
    onboarding_jtbd_values,
    onboarding_role_value,
)
from .records import save_result_table

DEFAULT_USAGE_CSV = "cases/case_usage.csv"
DEFAULT_SELECTION_JSON = "cases/industry_case_selection.json"
USAGE_HEADERS = [
    "case_index",
    "title",
    "industry",
    "status",
    "selected_at",
    "used_at",
    "last_run_at",
    "session_url",
    "share_url",
    "error",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select unused cases by industry and run Eureka generation.",
    )
    parser.add_argument(
        "cases_json",
        nargs="?",
        default="cases/500articles.json",
        help="Path to a JSON array, or an object with an items/cases/records array.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    parser.add_argument(
        "--per-industry",
        type=int,
        default=30,
        help="Maximum unused records to select for each industry.",
    )
    parser.add_argument(
        "--usage-csv",
        default=DEFAULT_USAGE_CSV,
        help="CSV file in cases/ used to track selected/used cases.",
    )
    parser.add_argument(
        "--selection-json",
        default=DEFAULT_SELECTION_JSON,
        help="JSON file used by --select-only to store the selected batch.",
    )
    parser.add_argument(
        "--records-csv",
        default=DEFAULT_CASE_RECORDS_CSV,
        help="CSV file used to append generated case records.",
    )
    parser.add_argument(
        "--results-json",
        default=DEFAULT_CASE_RESULTS_JSON,
        help="JSON file updated after each processed case.",
    )
    parser.add_argument(
        "--industries",
        default="",
        help="Optional comma-separated industry allowlist.",
    )
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Select cases, mark them as selected, and write selection JSON without calling Eureka.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print selected counts.")
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
    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="Command output format.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    if args.per_industry < 1:
        raise SystemExit("--per-industry must be greater than 0")

    records = load_case_records(args.cases_json)
    usage_rows = read_usage_rows(args.usage_csv)
    selected = select_unused_cases_by_industry(
        records=records,
        usage_rows=usage_rows,
        per_industry=args.per_industry,
        allowed_industries=_allowed_industries(args.industries),
    )

    if args.dry_run:
        print(_format_selection_summary(selected, usage_rows, as_json=args.output == "json", pretty=args.pretty))
        return

    if args.select_only:
        for items in selected.values():
            for case_index, item in items:
                mark_selected(usage_rows, case_index, item)
        write_usage_rows(usage_rows, args.usage_csv)
        selection_payload = build_selection_payload(
            cases_json=args.cases_json,
            usage_csv=args.usage_csv,
            selected=selected,
            per_industry=args.per_industry,
        )
        write_selection_json(selection_payload, args.selection_json)
        if args.output == "json":
            indent = 2 if args.pretty else None
            print(json.dumps(selection_payload, ensure_ascii=False, indent=indent))
        else:
            print(_format_select_only_summary(selection_payload, args.selection_json))
        return

    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    runtime = RuntimeDependencies(settings=settings)
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
    total = sum(len(items) for items in selected.values())
    processed = 0
    for industry, items in selected.items():
        for case_index, item in items:
            processed += 1
            mark_selected(usage_rows, case_index, item)
            write_usage_rows(usage_rows, args.usage_csv)
            print(
                f"[{processed}/{total}] industry={industry} case_index={case_index} "
                f"title={_string(item.get('title'))}",
                file=sys.stderr,
                flush=True,
            )

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
            result["source_industry"] = industry
            result["industry"] = onboarding_industry_value(industry)
            results.append(result)
            write_results_json(results=results, path=args.results_json)

            update_usage_after_run(usage_rows, case_index, item, result)
            write_usage_rows(usage_rows, args.usage_csv)
            if not result_has_required_urls(result):
                raise SystemExit(url_generation_error(result, args.results_json))
            if result.get("row"):
                save_result_table(row=result["row"], csv_path=args.records_csv, markdown_path="")

    output = {
        "cases_json": args.cases_json,
        "usage_csv": args.usage_csv,
        "processed": len(results),
        "success": sum(1 for item in results if item.get("curl_success")),
        "failed": sum(1 for item in results if not item.get("curl_success")),
        "records_csv": args.records_csv,
        "results_json": args.results_json,
        "selected_by_industry": {industry: len(items) for industry, items in selected.items()},
        "results": results,
    }
    if args.output == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(output, ensure_ascii=False, indent=indent))
    else:
        print(build_summary(output))
        print(f"usage_csv={args.usage_csv}")


def select_unused_cases_by_industry(
    records: list[dict[str, Any]],
    usage_rows: dict[int, dict[str, str]],
    per_industry: int = 30,
    allowed_industries: set[str] | None = None,
) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for record_index, item in enumerate(records):
        case_index = case_index_from_item(item, record_index)
        industry = _case_industry(item)
        if (
            allowed_industries
            and industry not in allowed_industries
            and onboarding_industry_value(industry) not in allowed_industries
        ):
            continue
        if _is_used(usage_rows.get(case_index)):
            continue
        if len(grouped[industry]) >= per_industry:
            continue
        grouped[industry].append((case_index, item))

    return dict(sorted(grouped.items(), key=lambda pair: pair[0]))


def build_selection_payload(
    cases_json: str,
    usage_csv: str,
    selected: dict[str, list[tuple[int, dict[str, Any]]]],
    per_industry: int,
) -> dict[str, Any]:
    items = []
    by_industry: dict[str, list[dict[str, Any]]] = {}
    for industry, selected_items in selected.items():
        industry_items = [_selection_item(case_index, item) for case_index, item in selected_items]
        by_industry[industry] = industry_items
        items.extend(industry_items)

    return {
        "cases_json": cases_json,
        "usage_csv": usage_csv,
        "generated_at": _now_iso(),
        "per_industry": per_industry,
        "total": len(items),
        "selected_by_industry": {industry: len(items) for industry, items in by_industry.items()},
        "items": items,
        "by_industry": by_industry,
    }


def write_selection_json(payload: dict[str, Any], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_usage_rows(path: str) -> dict[int, dict[str, str]]:
    usage_path = Path(path)
    if not usage_path.exists():
        return {}

    with usage_path.open("r", encoding="utf-8", newline="") as file:
        rows = {}
        for row in csv.DictReader(file):
            try:
                case_index = int(row.get("case_index", ""))
            except ValueError:
                continue
            rows[case_index] = {header: row.get(header, "") for header in USAGE_HEADERS}
        return rows


def write_usage_rows(rows: dict[int, dict[str, str]], path: str) -> None:
    usage_path = Path(path)
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    with usage_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=USAGE_HEADERS)
        writer.writeheader()
        for case_index in sorted(rows):
            row = rows[case_index]
            writer.writerow({header: row.get(header, "") for header in USAGE_HEADERS})


def _selection_item(case_index: int, item: dict[str, Any]) -> dict[str, Any]:
    source_industry = _case_industry(item)
    return {
        "case_index": case_index,
        "title": _string(item.get("title")),
        "source_industry": source_industry,
        "industry": onboarding_industry_value(source_industry),
        "categories": _string_list(item.get("categories")),
        "keywords": _string_list(item.get("keywords")),
        "description": _string(item.get("description")),
        "role": onboarding_role_value(item.get("role")),
        "jtbd": onboarding_jtbd_values(_string_list(item.get("jtbd"))),
        "date": _string(item.get("date")),
        "sub_industry": _string_list(item.get("sub_industry")),
        "output": _string(item.get("output")),
    }


def mark_selected(
    usage_rows: dict[int, dict[str, str]],
    case_index: int,
    item: dict[str, Any],
) -> None:
    now = _now_iso()
    row = usage_rows.get(case_index) or _base_usage_row(case_index, item)
    row["status"] = row.get("status") or "selected"
    row["selected_at"] = row.get("selected_at") or now
    usage_rows[case_index] = row


def update_usage_after_run(
    usage_rows: dict[int, dict[str, str]],
    case_index: int,
    item: dict[str, Any],
    result: dict[str, Any],
) -> None:
    now = _now_iso()
    row = usage_rows.get(case_index) or _base_usage_row(case_index, item)
    generated_urls = result_has_required_urls(result)
    row["status"] = "used" if generated_urls else "failed"
    row["last_run_at"] = now
    if generated_urls:
        row["used_at"] = now
    row["session_url"] = _string(result.get("session_url"))
    row["share_url"] = _string(result.get("share_url"))
    errors = result.get("errors") or []
    row["error"] = _string(errors[0]) if errors else ""
    usage_rows[case_index] = row


def _base_usage_row(case_index: int, item: dict[str, Any]) -> dict[str, str]:
    return {
        "case_index": str(case_index),
        "title": _string(item.get("title")),
        "industry": onboarding_industry_value(_case_industry(item)),
        "status": "",
        "selected_at": "",
        "used_at": "",
        "last_run_at": "",
        "session_url": "",
        "share_url": "",
        "error": "",
    }


def _format_selection_summary(
    selected: dict[str, list[tuple[int, dict[str, Any]]]],
    usage_rows: dict[int, dict[str, str]],
    as_json: bool = False,
    pretty: bool = False,
) -> str:
    payload = {
        "selected_total": sum(len(items) for items in selected.values()),
        "selected_by_industry": {industry: len(items) for industry, items in selected.items()},
        "used_total": sum(1 for row in usage_rows.values() if _is_used(row)),
    }
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)

    lines = [
        f"selected_total={payload['selected_total']}",
        f"used_total={payload['used_total']}",
    ]
    for industry, count in payload["selected_by_industry"].items():
        lines.append(f"{industry}={count}")
    return "\n".join(lines)


def _format_select_only_summary(payload: dict[str, Any], selection_json: str) -> str:
    lines = [
        f"selected_total={payload['total']}",
        f"selection_json={selection_json}",
        f"usage_csv={payload['usage_csv']}",
    ]
    for industry, count in payload["selected_by_industry"].items():
        lines.append(f"{industry}={count}")
    return "\n".join(lines)


def _auth_preflight_error(preflight: dict[str, Any]) -> str:
    reason = preflight.get("token_reason") or "authorization is not ready"
    if preflight.get("waited"):
        elapsed = float(preflight.get("elapsed_seconds") or 0)
        return (
            "Eureka authorization is still not ready after "
            f"{elapsed:.1f}s; copy a fresh api/eureka/query/conversational curl. "
            f"Reason: {reason}"
        )
    return (
        "Eureka authorization is not ready; run `uv run eureka-token import-curl --clipboard` "
        f"with a fresh api/eureka/query/conversational curl. Reason: {reason}"
    )


def _allowed_industries(raw: str) -> set[str] | None:
    values = {item.strip() for item in raw.split(",") if item.strip()}
    return values or None


def _case_industry(item: dict[str, Any]) -> str:
    return _string(item.get("source_industry")) or _string(item.get("industry")) or "unknown"


def _is_used(row: dict[str, str] | None) -> bool:
    return bool(row and row.get("status") == "used")


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
