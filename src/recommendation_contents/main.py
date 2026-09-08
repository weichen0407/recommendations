"""Command line entrypoint for the topic workflow graph."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .config import AppSettings, apply_env_file_to_process
from .graph import build_graph_with_dependencies
from .records import DEFAULT_RECORDS_CSV, DEFAULT_RECORDS_MARKDOWN, save_result_table


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the topic LangGraph workflow.")
    parser.add_argument("topic", help="Topic used to generate a complete prompt.")
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    parser.add_argument(
        "--context-json",
        default="{}",
        help="Additional request context as a JSON object.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output. Only applies when --output json is used.",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format.",
    )
    parser.add_argument(
        "--records-csv",
        default=DEFAULT_RECORDS_CSV,
        help="CSV file used to append every generated record.",
    )
    parser.add_argument(
        "--records-md",
        default=DEFAULT_RECORDS_MARKDOWN,
        help="Markdown table file regenerated from the CSV records.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not append this run to the records table files.",
    )
    args = parser.parse_args()

    context = _load_context(args.context_json)
    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    graph = build_graph_with_dependencies(settings=settings)
    result = graph.invoke(
        {
            "topic": args.topic,
            "request_context": context,
        }
    )
    rows = result.get("result_table_rows") or []
    if not args.no_save and rows:
        save_result_table(row=rows[0], csv_path=args.records_csv, markdown_path=args.records_md)

    if args.output == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(result, ensure_ascii=False, indent=indent))
    else:
        print(result.get("result_table_markdown") or "")


def _load_context(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--context-json must be valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise SystemExit("--context-json must be a JSON object")
    return value


if __name__ == "__main__":
    main()
