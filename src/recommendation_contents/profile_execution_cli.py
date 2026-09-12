"""Node 3 batch executor for reviewed profile-topic research prompts."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .brief_schema import load_brief_catalog, parse_brief_response
from .config import AppSettings, apply_env_file_to_process
from .nodes import RuntimeDependencies
from .research_prompt_generation import GenerationError
from .workflow_execution import execute_tasks, read_run
from .workflow_stages import validate_task_specs

NODE2_VERSION = "profile-topic-node2/1.0.0"
WORKFLOW_VERSION = "profile-topic-node3/1.0.0"
DEFAULT_JSON = Path("outputs/profile_topics/node3_eureka_results.json")
DEFAULT_CSV = Path("outputs/profile_topics/node3_eureka_results.csv")
DEFAULT_LOG = Path("outputs/profile_topics/node3_eureka_results.log")
DEFAULT_RUNS_DIR = Path("outputs/profile_topics/node3_runs")
AGGREGATE_CHECKPOINT_EVERY = 25

TERMINAL_ATTENTION_STATUSES = {"failed", "submission_unknown"}
ATTENTION_STATUSES = TERMINAL_ATTENTION_STATUSES | {"execution_error", "submitting"}
ACTIVE_STATUSES = {"prepared", "submitting", "needs_auth", "submitted", "pending", "running"}

CSV_COLUMNS = [
    "input",
    "generated_prompt",
    "session_url",
    "share_url",
    "format",
    "isCompleted",
    "completionStatus",
    "completionError",
    "title",
    "categories",
    "keywords",
    "description",
    "role",
    "industry",
    "jtbd",
    "date",
    "sub_industry",
    "row_no",
    "brief_id",
    "tag_set_id",
    "source_generation_id",
    "source_fingerprint",
    "question",
    "tags",
    "entities",
    "classification",
    "assumptions",
    "content_category",
    "research_instructions",
    "execution_status",
    "session_id",
    "share_id",
    "share_status",
    "share_error",
    "completion_status",
    "completion_poll_count",
    "errors",
    "run_record_path",
    "created_at",
    "updated_at",
]


class BatchFileError(ValueError):
    """Stable validation failure for a Node 2 or Node 3 checkpoint."""


def main(argv: list[str] | None = None) -> int:
    catalog = load_brief_catalog()
    parser = argparse.ArgumentParser(
        description=(
            "Node 3: submit successful profile-topic-node2 generated prompts to Eureka. "
            "The default mode creates sessions and shares without waiting for completion."
        )
    )
    parser.add_argument("input_json", type=Path, help="profile-topic-node2 JSON checkpoint")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=1)
    parser.add_argument("--max-tasks", type=int, default=0, help="Execute at most N pending prompts")
    parser.add_argument("--role", choices=_audience_values(catalog, "role"))
    parser.add_argument("--industry", choices=_audience_values(catalog, "industry"))
    parser.add_argument("--jtbd", choices=_audience_values(catalog, "jtbd"))
    parser.add_argument("--tag-set-id", action="append", default=[])
    parser.add_argument("--brief-id", action="append", default=[])
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--resume", action="store_true", help="Continue the existing checkpoint")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rebuild aggregate outputs while reusing matching per-task run records",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--wait-for-completion",
        action="store_true",
        help="Poll existing/new sessions until the configured completion wait limit",
    )
    args = parser.parse_args(argv)

    if args.resume and args.overwrite:
        parser.error("--resume and --overwrite cannot be combined")
    if args.max_tasks < 0:
        parser.error("--max-tasks must be non-negative")
    paths = [args.input_json, args.output_json, args.output_csv, args.log_file]
    if len({_resolved(path) for path in paths}) != len(paths):
        parser.error("Input, JSON, CSV and log paths must all be different")
    if _resolved(args.runs_dir) in {_resolved(path) for path in paths}:
        parser.error("--runs-dir must be different from the input and output files")

    if args.dry_run:
        return _run_locked(args, parser, catalog)
    try:
        with _batch_lock(args.output_json):
            return _run_locked(args, parser, catalog)
    except BatchFileError as exc:
        parser.error(str(exc))


def _run_locked(
    args: argparse.Namespace, parser: argparse.ArgumentParser, catalog: dict[str, Any]
) -> int:
    try:
        source = _load_json(args.input_json, "Node 2 input")
        tasks, failed_source_tag_sets = _validate_and_flatten_source(source, catalog)
    except ValueError as exc:
        parser.error(str(exc))

    selected = _select_tasks(
        tasks,
        role=args.role,
        industry=args.industry,
        jtbd=args.jtbd,
        tag_set_ids=set(args.tag_set_id),
        brief_ids=set(args.brief_id),
    )
    if not selected:
        parser.error("No successful Node 2 prompts match the filters")

    existing: dict[str, Any] | None = None
    if args.output_json.exists() and (args.resume or args.overwrite):
        try:
            existing = _load_json(args.output_json, "Node 3 checkpoint")
            existing = _validate_resume_document(
                existing, source, tasks, args.input_json, args.runs_dir
            )
        except ValueError as exc:
            parser.error(str(exc))
    elif args.resume and args.output_csv.exists():
        parser.error("Cannot resume from CSV alone; the Node 3 JSON checkpoint is missing")
    elif not args.resume and not args.overwrite and not args.dry_run:
        conflicts = [str(path) for path in (args.output_json, args.output_csv) if path.exists()]
        if conflicts:
            parser.error("Output exists; use --resume or --overwrite: " + ", ".join(conflicts))

    document = _new_document(source, args.input_json, args.runs_dir)
    by_id: dict[str, dict[str, Any]] = {}
    if existing is not None:
        by_id = {record["brief_id"]: record for record in existing["executions"]}
        if not args.overwrite:
            document = existing

    try:
        _assert_sources_unchanged(by_id, tasks)
        _reconcile_inner_runs(by_id, tasks, args.runs_dir)
    except ValueError as exc:
        parser.error(str(exc))

    candidates = [
        task
        for task in selected
        if _should_schedule(by_id.get(task["brief_id"]), args.wait_for_completion)
    ]
    scheduled = candidates[: args.max_tasks or None]
    bounded_pause = len(scheduled) < len(candidates)
    already_satisfied = len(selected) - len(candidates)

    document["source"] = _source_metadata(source, args.input_json)
    document["scope"] = _scope(tasks, failed_source_tag_sets, args.runs_dir)
    document["executions"] = _ordered_records(by_id, tasks)
    document["last_run"] = {
        "started_at": _now(),
        "finished_at": "",
        "status": "dry_run" if args.dry_run else "running",
        "wait_for_completion": args.wait_for_completion,
        "filters": {
            "role": args.role,
            "industry": args.industry,
            "jtbd": args.jtbd,
            "tag_set_ids": sorted(set(args.tag_set_id)),
            "brief_ids": sorted(set(args.brief_id)),
        },
        "selected_tasks": len(selected),
        "already_satisfied": already_satisfied,
        "pending_before_limit": len(candidates),
        "scheduled_tasks": len(scheduled),
        "max_tasks": args.max_tasks,
        "completed_tasks": 0,
        "failed_tasks": 0,
    }
    _update_progress(document, tasks)

    if args.dry_run:
        print(
            json.dumps(
                _summary(
                    document,
                    args,
                    selected,
                    already_satisfied,
                    scheduled,
                    bounded_pause,
                    dry_run=True,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    _prepare_log(args.log_file, append=bool(existing and not args.overwrite))
    document["status"] = "running"
    document["executions"] = _ordered_records(by_id, tasks)
    _save(document, args.output_json, args.output_csv, tasks)
    _log(
        f"call_curl_task: selected={len(selected)} already_satisfied={already_satisfied} "
        f"scheduled={len(scheduled)} remaining_after_limit={len(candidates) - len(scheduled)} "
        f"workers={args.workers} wait_for_completion={str(args.wait_for_completion).lower()}",
        args.log_file,
    )

    if not scheduled:
        _finish_document(
            document,
            tasks,
            paused=bounded_pause,
            wait_for_completion=args.wait_for_completion,
        )
        document["last_run"].update(finished_at=_now(), status=document["status"])
        _save(document, args.output_json, args.output_csv, tasks)
        summary = _summary(
            document,
            args,
            selected,
            already_satisfied,
            scheduled,
            bounded_pause,
        )
        _log("run_finished: " + json.dumps(summary, ensure_ascii=False), args.log_file)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return _exit_code(document, interrupted=False)

    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    local = threading.local()
    log_lock = threading.Lock()

    def runtime_for_thread() -> RuntimeDependencies:
        if not hasattr(local, "runtime"):
            local.runtime = RuntimeDependencies(settings=settings)
        return local.runtime

    def execute(task: dict[str, Any]) -> dict[str, Any]:
        run_record_path = _task_run_path(args.runs_dir, task["brief_id"])
        last_marker: tuple[Any, ...] | None = None

        def on_update(results: list[dict[str, Any]]) -> None:
            nonlocal last_marker
            result = results[0]
            marker = (
                result.get("status"),
                result.get("share_status"),
                result.get("completion_status"),
                result.get("completion_poll_count", 0),
            )
            if marker == last_marker:
                return
            last_marker = marker
            with log_lock:
                _log(
                    f"task_update brief_id={task['brief_id']} status={marker[0]} "
                    f"share_status={marker[1]} completion_status={marker[2] or ''} "
                    f"polls={marker[3]}",
                    args.log_file,
                )

        try:
            results, _ = execute_tasks(
                _execution_generation(task),
                [task["task_spec"]],
                runtime_for_thread(),
                run_record_path,
                wait_for_completion=args.wait_for_completion,
                on_update=on_update,
            )
            return _record_from_result(
                task, results[0], run_record_path, by_id.get(task["brief_id"])
            )
        except Exception as exc:  # noqa: BLE001 - retain a restartable provider boundary
            recovered = _result_from_inner_run(task, run_record_path)
            if recovered is not None and recovered.get("status") != "prepared":
                return _record_from_result(
                    task, recovered, run_record_path, by_id.get(task["brief_id"])
                )
            return _execution_error_record(
                task, run_record_path, type(exc).__name__, by_id.get(task["brief_id"])
            )

    completed = failed_this_run = 0
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=args.workers)
    futures = {executor.submit(execute, task): task for task in scheduled}
    handled: set[Any] = set()
    interrupted = False
    second_interrupt = False

    def commit(future: Any) -> None:
        nonlocal completed, failed_this_run
        task = futures[future]
        record = future.result()
        handled.add(future)
        by_id[task["brief_id"]] = record
        completed += 1
        if _record_needs_attention(record):
            failed_this_run += 1
        document["executions"] = _ordered_records(by_id, tasks)
        document["last_run"].update(
            completed_tasks=completed,
            failed_tasks=failed_this_run,
        )
        _update_progress(document, tasks)
        if completed % AGGREGATE_CHECKPOINT_EVERY == 0:
            _save(document, args.output_json, args.output_csv, tasks, write_csv=False)
        _log(
            _progress_line(
                selected_total=len(selected),
                already_satisfied=already_satisfied,
                completed=completed,
                failed_this_run=failed_this_run,
                elapsed_seconds=time.monotonic() - started,
                task=task,
                record=record,
            ),
            args.log_file,
        )

    try:
        for future in as_completed(futures):
            commit(future)
    except KeyboardInterrupt:
        interrupted = True
        document["status"] = "paused"
        document["last_run"]["status"] = "stopping"
        _save(document, args.output_json, args.output_csv, tasks)
        for future in futures:
            if future not in handled:
                future.cancel()
        remaining = [
            future for future in futures if future not in handled and not future.cancelled()
        ]
        _log(
            "Stop requested; queued tasks were cancelled. Waiting for "
            f"{len(remaining)} in-flight task(s) so their run records can be checkpointed.",
            args.log_file,
        )
        try:
            for future in as_completed(remaining):
                commit(future)
        except KeyboardInterrupt:
            second_interrupt = True
            _log(
                "Second stop requested; leaving after the latest completed checkpoint.",
                args.log_file,
            )
    finally:
        executor.shutdown(wait=not second_interrupt, cancel_futures=interrupted)

    _finish_document(
        document,
        tasks,
        paused=interrupted or bounded_pause,
        wait_for_completion=args.wait_for_completion,
    )
    document["last_run"].update(
        finished_at=_now(),
        status=document["status"],
        completed_tasks=completed,
        failed_tasks=failed_this_run,
    )
    _save(document, args.output_json, args.output_csv, tasks)
    summary = _summary(
        document,
        args,
        selected,
        already_satisfied,
        scheduled,
        bounded_pause,
        interrupted=interrupted,
    )
    _log("run_finished: " + json.dumps(summary, ensure_ascii=False), args.log_file)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return _exit_code(document, interrupted=interrupted)


@contextmanager
def _batch_lock(output_json: Path):
    lock_path = output_json.with_name(output_json.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BatchFileError(
                f"Node 3 checkpoint is already executing: {output_json}"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _audience_values(catalog: dict[str, Any], key: str) -> list[str]:
    return [item["value"] for item in catalog["audience"][key]]


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = parse_brief_response(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise BatchFileError(f"Cannot read {label} {path} ({type(exc).__name__}).") from exc
    if not isinstance(value, dict):
        raise BatchFileError(f"{label} must contain a JSON object")
    return value


def _validate_and_flatten_source(
    document: dict[str, Any], catalog: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    if document.get("workflow_version") != NODE2_VERSION:
        raise BatchFileError(f"Input must use {NODE2_VERSION}")
    if document.get("stage") != "generate_research_prompt":
        raise BatchFileError("Input stage must be generate_research_prompt")
    if document.get("taxonomy_version") != catalog["taxonomy_version"]:
        raise BatchFileError("Node 2 input uses a different taxonomy version")
    if not isinstance(document.get("created_at"), str) or not document["created_at"]:
        raise BatchFileError("Node 2 input created_at is required")
    generations = document.get("generations")
    if not isinstance(generations, list):
        raise BatchFileError("Node 2 input generations must be an array")

    tasks: list[dict[str, Any]] = []
    seen_brief_ids: set[str] = set()
    failed_source_tag_sets = 0
    for index, generation in enumerate(generations):
        if not isinstance(generation, dict):
            raise BatchFileError(f"generations[{index}] must be an object")
        if generation.get("status") != "succeeded":
            failed_source_tag_sets += 1
            continue
        tag_set_id = generation.get("tag_set_id")
        if not isinstance(tag_set_id, str) or not tag_set_id:
            raise BatchFileError(f"generations[{index}].tag_set_id is required")
        if generation.get("errors") != []:
            raise BatchFileError(f"{tag_set_id}: successful generation must have no errors")
        source_generation_id = generation.get("source_generation_id")
        if not _is_uuid(source_generation_id):
            raise BatchFileError(f"{tag_set_id}: source_generation_id must be a UUID")
        source_fingerprint = generation.get("source_fingerprint")
        if not isinstance(source_fingerprint, str) or not source_fingerprint:
            raise BatchFileError(f"{tag_set_id}: source_fingerprint is required")
        request = generation.get("input")
        briefs = generation.get("briefs")
        specs = generation.get("task_specs")
        output_format = generation.get("format")
        if not isinstance(request, dict) or not isinstance(briefs, list):
            raise BatchFileError(f"{tag_set_id}: input and briefs are required")
        try:
            validate_task_specs(
                {"input": request, "briefs": briefs},
                specs,
                output_format,
                "call_curl_task",
            )
        except (GenerationError, KeyError, TypeError) as exc:
            errors = exc.errors if isinstance(exc, GenerationError) else [type(exc).__name__]
            raise BatchFileError(f"{tag_set_id}: invalid task_specs: {'; '.join(errors[:5])}") from exc
        if not specs:
            raise BatchFileError(f"{tag_set_id}: successful generation has no task_specs")

        audience = request.get("audience")
        if not isinstance(audience, dict):
            raise BatchFileError(f"{tag_set_id}: input.audience must be an object")
        for spec in specs:
            brief_id = spec.get("brief_id")
            if not _is_uuid(brief_id):
                raise BatchFileError(f"{tag_set_id}: every brief_id must be a UUID")
            if brief_id in seen_brief_ids:
                raise BatchFileError(f"Duplicate brief_id across Node 2: {brief_id}")
            seen_brief_ids.add(brief_id)
            task = {
                "source_row_no": len(tasks) + 1,
                "brief_id": brief_id,
                "tag_set_id": tag_set_id,
                "source_generation_id": source_generation_id,
                "node1_source_fingerprint": source_fingerprint,
                "input": request,
                "role": audience.get("role", ""),
                "industry": audience.get("industry", ""),
                "jtbd": audience.get("jtbd", ""),
                "format": output_format,
                "research_prompt_generated_at": generation.get(
                    "research_prompt_generated_at", ""
                ),
                "task_spec": spec,
            }
            task["source_fingerprint"] = _task_fingerprint(task)
            tasks.append(task)
    if not tasks:
        raise BatchFileError("Node 2 input contains no successful executable prompts")
    return tasks, failed_source_tag_sets


def _task_fingerprint(task: dict[str, Any]) -> str:
    value = {
        "tag_set_id": task["tag_set_id"],
        "source_generation_id": task["source_generation_id"],
        "node1_source_fingerprint": task["node1_source_fingerprint"],
        "input": task["input"],
        "format": task["format"],
        "task_spec": task["task_spec"],
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_dataset_id(source: dict[str, Any]) -> str:
    value = {
        "workflow_version": source.get("workflow_version"),
        "created_at": source.get("created_at"),
        "taxonomy_version": source.get("taxonomy_version"),
        "node1_dataset_id": (source.get("source") or {}).get("dataset_id"),
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _source_metadata(source: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "dataset_id": _source_dataset_id(source),
        "json_path": str(path.resolve()),
        "workflow_version": source["workflow_version"],
        "created_at": source["created_at"],
        "updated_at": source.get("updated_at", ""),
        "status": source.get("status", ""),
    }


def _scope(
    tasks: list[dict[str, Any]], failed_source_tag_sets: int, runs_dir: Path
) -> dict[str, Any]:
    return {
        "eligible_tasks": len(tasks),
        "successful_source_tag_sets": len({task["tag_set_id"] for task in tasks}),
        "failed_source_tag_sets": failed_source_tag_sets,
        "runs_dir": str(runs_dir.resolve()),
        "formats": sorted({task["format"] for task in tasks}),
    }


def _new_document(source: dict[str, Any], source_path: Path, runs_dir: Path) -> dict[str, Any]:
    now = _now()
    return {
        "workflow_version": WORKFLOW_VERSION,
        "stage": "call_curl_task",
        "status": "paused",
        "created_at": now,
        "updated_at": now,
        "taxonomy_version": source["taxonomy_version"],
        "source": _source_metadata(source, source_path),
        "scope": _scope([], 0, runs_dir),
        "progress": {},
        "last_run": {},
        "executions": [],
    }


def _validate_resume_document(
    document: dict[str, Any],
    source: dict[str, Any],
    tasks: list[dict[str, Any]],
    source_path: Path,
    runs_dir: Path,
) -> dict[str, Any]:
    if document.get("workflow_version") != WORKFLOW_VERSION:
        raise BatchFileError(f"Resume output must use {WORKFLOW_VERSION}")
    if document.get("stage") != "call_curl_task":
        raise BatchFileError("Resume output stage must be call_curl_task")
    if document.get("taxonomy_version") != source["taxonomy_version"]:
        raise BatchFileError("Resume output and Node 2 input use different taxonomy versions")
    metadata = document.get("source")
    if not isinstance(metadata, dict) or metadata.get("dataset_id") != _source_dataset_id(source):
        raise BatchFileError("Resume output belongs to a different Node 2 dataset")
    scope = document.get("scope")
    if not isinstance(scope, dict):
        raise BatchFileError("Resume output scope must be an object")
    saved_runs_dir = scope.get("runs_dir")
    if saved_runs_dir and _resolved(Path(saved_runs_dir)) != _resolved(runs_dir):
        raise BatchFileError("--runs-dir does not match the Node 3 checkpoint")
    executions = document.get("executions")
    if not isinstance(executions, list):
        raise BatchFileError("Resume output executions must be an array")
    seen: set[str] = set()
    for index, record in enumerate(executions):
        if not isinstance(record, dict):
            raise BatchFileError(f"executions[{index}] must be an object")
        brief_id = record.get("brief_id")
        if not _is_uuid(brief_id) or brief_id in seen:
            raise BatchFileError("Resume output has a missing or duplicate brief_id")
        seen.add(brief_id)
        if not isinstance(record.get("source_fingerprint"), str):
            raise BatchFileError(f"{brief_id}: source_fingerprint is required")
    task_ids = {task["brief_id"] for task in tasks}
    missing = seen - task_ids
    if missing:
        raise BatchFileError(
            "Node 2 no longer contains previously executed brief_id: " + min(missing)
        )
    document["source"] = _source_metadata(source, source_path)
    return document


def _assert_sources_unchanged(
    records: dict[str, dict[str, Any]], tasks: list[dict[str, Any]]
) -> None:
    tasks_by_id = {task["brief_id"]: task for task in tasks}
    for brief_id, record in records.items():
        task = tasks_by_id.get(brief_id)
        if task is None:
            raise BatchFileError(f"Node 2 no longer contains executed brief_id {brief_id}")
        if record.get("source_fingerprint") != task["source_fingerprint"]:
            raise BatchFileError(
                f"{brief_id}: source prompt changed after an execution record was created; "
                "use a new Node 3 output and runs directory"
            )


def _select_tasks(
    tasks: Iterable[dict[str, Any]],
    *,
    role: str | None,
    industry: str | None,
    jtbd: str | None,
    tag_set_ids: set[str],
    brief_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        task
        for task in tasks
        if (role is None or task["role"] == role)
        and (industry is None or task["industry"] == industry)
        and (jtbd is None or task["jtbd"] == jtbd)
        and (not tag_set_ids or task["tag_set_id"] in tag_set_ids)
        and (not brief_ids or task["brief_id"] in brief_ids)
    ]


def _ordered_records(
    records: dict[str, dict[str, Any]], tasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_order = {task["brief_id"]: task["source_row_no"] for task in tasks}
    return sorted(
        records.values(),
        key=lambda record: source_order.get(record["brief_id"], record.get("source_row_no", 0)),
    )


def _task_run_path(runs_dir: Path, brief_id: str) -> Path:
    return runs_dir / f"{UUID(brief_id)}.json"


def _execution_generation(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_version": WORKFLOW_VERSION,
        "status": "succeeded",
        "generation_id": task["source_generation_id"],
        "tag_set_id": task["tag_set_id"],
        "source_fingerprint": task["source_fingerprint"],
        "input": task["input"],
        "briefs": [task["task_spec"]["brief"]],
    }


def _reconcile_inner_runs(
    records: dict[str, dict[str, Any]], tasks: list[dict[str, Any]], runs_dir: Path
) -> None:
    for task in tasks:
        brief_id = task["brief_id"]
        path = _task_run_path(runs_dir, brief_id)
        if path.exists():
            try:
                saved = read_run(path)
            except (OSError, ValueError, TypeError) as exc:
                raise BatchFileError(f"Cannot read inner run {path} ({type(exc).__name__})") from exc
            if saved.get("task_specs") != [task["task_spec"]]:
                raise BatchFileError(
                    f"{brief_id}: source prompt changed after the inner execution began; "
                    "use a new Node 3 output and runs directory"
                )
            results = saved.get("results")
            if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
                raise BatchFileError(f"{brief_id}: inner run has invalid results")
            records[brief_id] = _record_from_result(
                task, results[0], path, records.get(brief_id)
            )
            continue
        record = records.get(brief_id)
        if record and _record_has_external_state(record):
            raise BatchFileError(
                f"{brief_id}: inner run record is missing; refusing a possible duplicate submission"
            )


def _result_from_inner_run(task: dict[str, Any], path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        saved = read_run(path)
    except (OSError, ValueError, TypeError):
        return None
    if saved.get("task_specs") != [task["task_spec"]]:
        return None
    results = saved.get("results")
    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], dict):
        return results[0]
    return None


def _prepared_record(task: dict[str, Any], runs_dir: Path) -> dict[str, Any]:
    return _record_from_result(
        task,
        {
            "status": "prepared",
            "session_id": "",
            "session_url": "",
            "share_id": "",
            "share_url": "",
            "share_status": "pending",
            "isCompleted": False,
            "completion_status": "",
            "completion_poll_count": 0,
            "errors": [],
        },
        _task_run_path(runs_dir, task["brief_id"]),
        None,
    )


def _record_from_result(
    task: dict[str, Any],
    result: dict[str, Any],
    run_record_path: Path,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    spec = task["task_spec"]
    brief = spec["brief"]
    now = _now()
    tags = brief["tags"]
    generated_date = str(task["research_prompt_generated_at"])[:10]
    return {
        "source_row_no": task["source_row_no"],
        "brief_id": task["brief_id"],
        "tag_set_id": task["tag_set_id"],
        "source_generation_id": task["source_generation_id"],
        "source_fingerprint": task["source_fingerprint"],
        "role": task["role"],
        "industry": task["industry"],
        "jtbd": task["jtbd"],
        "format": task["format"],
        "title": brief["title"],
        "description": brief["description"],
        "input": brief["title"],
        "categories": [spec["content_category"]],
        "date": generated_date,
        "sub_industry": [tags["industry_segment"]] if tags["industry_segment"] else [],
        "tags": tags,
        "entities": brief["entities"],
        "keywords": brief["keywords"],
        "classification": brief["classification"],
        "assumptions": brief["assumptions"],
        "content_category": spec["content_category"],
        "research_instructions": spec["research_instructions"],
        "generated_prompt": spec["generated_prompt"],
        "research_prompt_generated_at": task["research_prompt_generated_at"],
        "execution_status": result.get("status", "prepared"),
        "session_id": result.get("session_id", ""),
        "session_url": result.get("session_url", ""),
        "share_id": result.get("share_id", ""),
        "share_url": result.get("share_url", ""),
        "share_status": result.get("share_status", "pending"),
        "share_error": result.get("share_error", ""),
        "isCompleted": bool(result.get("isCompleted", False)),
        "completion_status": result.get("completion_status", ""),
        "completion_poll_count": result.get("completion_poll_count", 0),
        "errors": [str(error)[:2000] for error in result.get("errors", [])],
        "run_record_path": str(run_record_path.resolve()),
        "created_at": (previous or {}).get("created_at", now),
        "updated_at": now,
    }


def _execution_error_record(
    task: dict[str, Any],
    path: Path,
    error_type: str,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _prepared_record(task, path.parent)
    if previous:
        record["created_at"] = previous.get("created_at", record["created_at"])
    record.update(
        execution_status="execution_error",
        errors=[f"Node 3 execution failed ({error_type}); resume this task."],
        updated_at=_now(),
    )
    return record


def _record_has_external_state(record: dict[str, Any]) -> bool:
    return bool(
        record.get("session_id")
        or record.get("share_id")
        or record.get("execution_status")
        in {"submitting", "submitted", "pending", "running", "completed", "submission_unknown"}
    )


def _should_schedule(record: dict[str, Any] | None, wait_for_completion: bool) -> bool:
    if record is None:
        return True
    status = record.get("execution_status", "prepared")
    if status in TERMINAL_ATTENTION_STATUSES:
        return False
    if record.get("share_status") == "submission_unknown" and not wait_for_completion:
        return False
    if wait_for_completion:
        return status != "completed" or not record.get("isCompleted", False)
    if (
        record.get("session_id")
        and record.get("share_status") != "pending"
        and status in {"submitted", "pending", "running", "completed"}
    ):
        return False
    return status in ACTIVE_STATUSES or status == "execution_error"


def _record_needs_attention(record: dict[str, Any]) -> bool:
    return bool(
        record.get("execution_status") in ATTENTION_STATUSES
        or record.get("share_status") in {"submission_unknown", "unavailable"}
        or record.get("errors")
        and record.get("execution_status") == "needs_auth"
    )


def _update_progress(document: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    fingerprints = {task["brief_id"]: task["source_fingerprint"] for task in tasks}
    records = [
        record
        for record in document.get("executions", [])
        if fingerprints.get(record.get("brief_id")) == record.get("source_fingerprint")
    ]
    counts = Counter(record.get("execution_status", "prepared") for record in records)
    progress = {
        "eligible_tasks": len(tasks),
        "tracked_tasks": len(records),
        "unstarted_tasks": len(tasks) - len(records),
        "prepared_tasks": counts["prepared"],
        "submitted_tasks": counts["submitted"],
        "pending_tasks": counts["pending"] + counts["running"],
        "completed_tasks": counts["completed"],
        "needs_auth_tasks": counts["needs_auth"],
        "failed_tasks": counts["failed"] + counts["execution_error"],
        "submitting_tasks": counts["submitting"],
        "execution_error_tasks": counts["execution_error"],
        "share_unavailable_tasks": sum(
            record.get("share_status") == "unavailable" for record in records
        ),
        "submission_unknown_tasks": sum(
            record.get("execution_status") == "submission_unknown"
            or record.get("share_status") == "submission_unknown"
            for record in records
        ),
    }
    document["progress"] = progress
    document["updated_at"] = _now()
    return progress


def _finish_document(
    document: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    paused: bool,
    wait_for_completion: bool,
) -> None:
    progress = _update_progress(document, tasks)
    records = document.get("executions", [])
    attention = any(_record_needs_attention(record) for record in records)
    if attention:
        document["status"] = "failed"
    elif (
        paused
        or progress["unstarted_tasks"]
        or progress["prepared_tasks"]
        or progress["needs_auth_tasks"]
        or wait_for_completion
        and any(
            record.get("execution_status") != "completed"
            or not record.get("isCompleted", False)
            for record in records
        )
    ):
        document["status"] = "paused"
    else:
        document["status"] = "succeeded"


def _save(
    document: dict[str, Any],
    json_path: Path,
    csv_path: Path,
    tasks: list[dict[str, Any]],
    *,
    write_csv: bool = True,
) -> None:
    document["updated_at"] = _now()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_name(f".{json_path.name}.{uuid4()}.tmp")
    csv_tmp = csv_path.with_name(f".{csv_path.name}.{uuid4()}.tmp") if write_csv else None
    try:
        with json_tmp.open("w", encoding="utf-8") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(json_tmp, json_path)
        if csv_tmp is not None:
            with csv_tmp.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(_rows(document, tasks))
                file.flush()
                os.fsync(file.fileno())
            os.replace(csv_tmp, csv_path)
    finally:
        json_tmp.unlink(missing_ok=True)
        if csv_tmp is not None:
            csv_tmp.unlink(missing_ok=True)


def _rows(
    document: dict[str, Any], tasks: list[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    task_ids = {task["brief_id"] for task in tasks}
    records = [
        record for record in document.get("executions", []) if record.get("brief_id") in task_ids
    ]
    for row_no, record in enumerate(
        sorted(records, key=lambda item: item.get("source_row_no", 0)), 1
    ):
        yield {
            "input": record["input"],
            "generated_prompt": record["generated_prompt"],
            "session_url": record["session_url"],
            "share_url": record["share_url"],
            "format": record["format"],
            "isCompleted": str(record["isCompleted"]).lower(),
            "completionStatus": record["completion_status"],
            "completionError": "; ".join(record["errors"]),
            "title": record["title"],
            "categories": _json_cell(record["categories"]),
            "keywords": _json_cell(record["keywords"]),
            "description": record["description"],
            "role": record["role"],
            "industry": record["industry"],
            "jtbd": _json_cell([record["jtbd"]]),
            "date": record["date"],
            "sub_industry": _json_cell(record["sub_industry"]),
            "row_no": row_no,
            "brief_id": record["brief_id"],
            "tag_set_id": record["tag_set_id"],
            "source_generation_id": record["source_generation_id"],
            "source_fingerprint": record["source_fingerprint"],
            "question": record["title"],
            "tags": _json_cell(record["tags"]),
            "entities": _json_cell(record["entities"]),
            "classification": _json_cell(record["classification"]),
            "assumptions": _json_cell(record["assumptions"]),
            "content_category": record["content_category"],
            "research_instructions": record["research_instructions"],
            "execution_status": record["execution_status"],
            "session_id": record["session_id"],
            "share_id": record["share_id"],
            "share_status": record["share_status"],
            "share_error": record["share_error"],
            "completion_status": record["completion_status"],
            "completion_poll_count": record["completion_poll_count"],
            "errors": _json_cell(record["errors"]),
            "run_record_path": record["run_record_path"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }


def _summary(
    document: dict[str, Any],
    args: argparse.Namespace,
    selected: list[dict[str, Any]],
    already_satisfied: int,
    scheduled: list[dict[str, Any]],
    bounded_pause: bool,
    *,
    dry_run: bool = False,
    interrupted: bool = False,
) -> dict[str, Any]:
    return {
        "node": "call_curl_task",
        "status": "dry_run" if dry_run else document["status"],
        "source_json": str(args.input_json),
        "output_json": str(args.output_json),
        "output_csv": str(args.output_csv),
        "log_file": str(args.log_file),
        "runs_dir": str(args.runs_dir),
        "wait_for_completion": args.wait_for_completion,
        "source_status": document["source"].get("status", ""),
        "successful_source_tag_sets": document["scope"].get(
            "successful_source_tag_sets", 0
        ),
        "failed_source_tag_sets": document["scope"].get("failed_source_tag_sets", 0),
        "selected_tasks": len(selected),
        "already_satisfied": already_satisfied,
        "scheduled_tasks": len(scheduled),
        "bounded_pause": bounded_pause,
        "interrupted": interrupted,
        **document["progress"],
    }


def _progress_line(
    *,
    selected_total: int,
    already_satisfied: int,
    completed: int,
    failed_this_run: int,
    elapsed_seconds: float,
    task: dict[str, Any],
    record: dict[str, Any],
) -> str:
    processed = already_satisfied + completed
    percent = 100 * processed / selected_total if selected_total else 100.0
    remaining = max(selected_total - processed, 0)
    eta = elapsed_seconds * remaining / completed if completed else None
    errors = record.get("errors") or []
    error = f" | {_short(errors[0], 160)}" if errors else ""
    return (
        f"[{processed}/{selected_total} | {percent:5.1f}%] completed_this_run={completed} "
        f"attention={failed_this_run} elapsed={_duration(elapsed_seconds)} eta={_duration(eta)} "
        f"brief_id={task['brief_id']} status={record['execution_status']} "
        f"title={json.dumps(_short(record['title'], 80), ensure_ascii=False)}{error}"
    )


def _prepare_log(path: Path, *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not append:
        path.write_text("", encoding="utf-8")


def _log(message: str, path: Path) -> None:
    line = f"{_now()} {message}"
    print(line, file=sys.stderr, flush=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
        file.flush()


def _exit_code(document: dict[str, Any], *, interrupted: bool) -> int:
    if interrupted:
        return 130
    progress = document.get("progress") or {}
    return 1 if (
        progress.get("failed_tasks", 0)
        or progress.get("submission_unknown_tasks", 0)
        or progress.get("submitting_tasks", 0)
        or progress.get("needs_auth_tasks", 0)
        or progress.get("share_unavailable_tasks", 0)
    ) else 0


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _short(value: Any, limit: int) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _resolved(path: Path) -> str:
    return str(path.expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
