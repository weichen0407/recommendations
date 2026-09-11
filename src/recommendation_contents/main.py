"""Command line entrypoint for the topic workflow graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import AppSettings, apply_env_file_to_process
from .graph import build_graph_with_dependencies
from .records import DEFAULT_RECORDS_CSV, DEFAULT_RECORDS_MARKDOWN, save_result_table
from .summary_generation import GenerationError
from .workflow_execution import DEFAULT_RUNS_DIR, write_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the topic LangGraph workflow.")
    parser.add_argument(
        "topic", nargs="?", help="Idea used by generate_topic and generate_summary."
    )
    parser.add_argument("--language", choices=["zh-CN", "en"], default=None)
    parser.add_argument("--format", choices=["html", "report"], default=None)
    parser.add_argument("--count", type=int, choices=range(1, 11), default=None)
    parser.add_argument(
        "--from-stage-file",
        type=Path,
        help="Continue from a reviewed topic or summary JSON file, reusing generated content.",
    )
    parser.add_argument(
        "--stop-after",
        choices=["generate_topic", "generate_summary"],
        help="Save this stage for inspection and exit before executing downstream nodes.",
    )
    parser.add_argument(
        "--stage-output",
        type=Path,
        help="Stage snapshot path (requires --stop-after; defaults to outputs/workflow_stages/).",
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--resume-run-id", default="", help="Resume a saved run without regenerating prompts."
    )
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
    args = parser.parse_args(argv)
    if (
        sum([args.topic is not None, bool(args.resume_run_id), args.from_stage_file is not None])
        != 1
    ):
        parser.error("Provide exactly one of topic, --resume-run-id or --from-stage-file")
    if args.resume_run_id and args.no_save:
        parser.error("--resume-run-id cannot be combined with --no-save")
    if args.from_stage_file and (args.count is not None or args.language is not None):
        parser.error(
            "--from-stage-file preserves the saved language and count; edit the file instead"
        )
    if args.stage_output and not args.stop_after:
        parser.error("--stage-output requires --stop-after")

    stage_result = None
    if args.from_stage_file:
        try:
            stage_result = json.loads(args.from_stage_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            parser.error("Cannot read --from-stage-file as JSON")
        if not isinstance(stage_result, dict):
            parser.error("--from-stage-file must contain a JSON object")

    context = _load_context(args.context_json)
    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    graph_options = {}
    config = {"run_name": "topic_workflow"}
    invoke_options = {}
    if args.stop_after:
        from langgraph.checkpoint.memory import InMemorySaver

        graph_options["checkpointer"] = InMemorySaver()
        config["configurable"] = {"thread_id": str(uuid4())}
        invoke_options["interrupt_after"] = [args.stop_after]
    graph = build_graph_with_dependencies(
        settings=settings,
        runs_dir=None if args.no_save else args.runs_dir,
        **graph_options,
    )
    input_data = {
        "topic": args.topic,
        "request_context": context,
        "count": args.count if args.count is not None else 1,
        "resume_run_id": args.resume_run_id,
    }
    if stage_result is not None:
        input_data["stage_result"] = stage_result
    if args.language:
        input_data["language"] = args.language
    if args.format:
        input_data["format"] = args.format
    try:
        result = graph.invoke(input_data, config=config, **invoke_options)
    except GenerationError as exc:
        print(
            json.dumps(
                {"status": "failed", "stage": exc.stage, "errors": exc.errors}, ensure_ascii=False
            )
        )
        return 1
    if args.stop_after:
        path = args.stage_output or (
            Path("outputs/workflow_stages")
            / f"{result['generation_result']['generation_id']}.{args.stop_after}.json"
        )
        result.update(status="paused", stopped_after=args.stop_after, stage_output_path=str(path))
        write_run(path, result)
        if args.output == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        else:
            print(f"Paused after {args.stop_after}. Review: {path}")
        return 0
    rows = result.get("result_table_rows") or []
    if not args.no_save and rows:
        for row in rows:
            save_result_table(row=row, csv_path=args.records_csv, markdown_path=args.records_md)

    if args.output == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(result, ensure_ascii=False, indent=indent))
    else:
        print(result.get("result_table_markdown") or "")
    return 0 if result.get("status") == "succeeded" else 1


def _load_context(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--context-json must be valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise SystemExit("--context-json must be a JSON object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
