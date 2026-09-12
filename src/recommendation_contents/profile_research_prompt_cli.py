"""Batch Node 2: turn profile-topic batches into reviewable research prompts.

The command reads a ``profile-topic-node1`` JSON document and writes a separate,
restartable Node 2 checkpoint.  It deliberately has no Eureka dependency: its
last output is ``task_specs[].generated_prompt`` for a later execution stage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .brief_schema import SCHEMA_VERSION, load_brief_catalog, parse_brief_response
from .config import OpenAISettings, apply_env_file_to_process, merged_env
from .llm import create_chat_model
from .profile_topic_generation import (
    profile_tag_set_id,
    triple_id,
    validate_profile_briefs,
    validate_profile_request,
)
from .research_prompt_generation import (
    GenerationError,
    build_task_spec,
    generate_research_prompt_specs,
    validate_research_prompts,
)

NODE1_VERSION = "profile-topic-node1/4.0.0"
WORKFLOW_VERSION = "profile-topic-node2/1.0.0"
DEFAULT_JSON = Path("outputs/profile_topics/node2_research_prompts.json")
DEFAULT_CSV = Path("outputs/profile_topics/node2_research_prompts.csv")

CSV_COLUMNS = [
    "row_no",
    "triple_id",
    "tag_set_id",
    "case_no",
    "role",
    "industry",
    "jtbd",
    "question",
    "description",
    "topic_theme",
    "question_intent",
    "scope_level",
    "role_perspective",
    "industry_segment",
    "jtbd_task",
    "desired_output",
    "entities",
    "keywords",
    "classification_rationale",
    "industry_status",
    "assumptions",
    "content_category",
    "research_instructions",
    "generated_prompt",
    "format",
    "research_prompt_status",
    "research_prompt_errors",
    "research_prompt_attempts",
    "execution_status",
    "session_url",
    "share_url",
    "brief_id",
    "source_generation_id",
    "taxonomy_version",
    "topic_generated_at",
    "research_prompt_generated_at",
]


class BatchFileError(ValueError):
    """A stable, user-facing validation error for a batch checkpoint."""


def main(argv: list[str] | None = None) -> int:
    catalog = load_brief_catalog()
    parser = argparse.ArgumentParser(
        description=(
            "Node 2: batch-generate research prompts from successful profile-topic-node1 "
            "tag sets. This command never calls Eureka."
        )
    )
    parser.add_argument("input_json", type=Path, help="The profile-topic-node1 JSON checkpoint.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--format", choices=["html", "report"], default=None)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=4)
    parser.add_argument("--role", choices=_audience_values(catalog, "role"))
    parser.add_argument("--industry", choices=_audience_values(catalog, "industry"))
    parser.add_argument("--jtbd", choices=_audience_values(catalog, "jtbd"))
    parser.add_argument(
        "--tag-set-id",
        action="append",
        default=[],
        help="Process only this exact tag_set_id; repeat to select several.",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help=(
            "Run at most N pending tag-set batches, after filters and resume checks. "
            "Zero means all pending batches."
        ),
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Keep current successful batches and retry failed, stale, or missing batches.",
    )
    parser.add_argument(
        "--regenerate-selected",
        action="store_true",
        help="With --resume, regenerate successful batches selected by the filters.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Start a new Node 2 output.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the pending scope without writing files or calling the model.",
    )
    args = parser.parse_args(argv)

    if args.resume and args.overwrite:
        parser.error("--resume and --overwrite cannot be combined")
    if args.regenerate_selected and not args.resume:
        parser.error("--regenerate-selected requires --resume")
    if args.max_batches < 0:
        parser.error("--max-batches must be non-negative")
    if _same_path(args.input_json, args.output_json) or _same_path(
        args.input_json, args.output_csv
    ):
        parser.error("Node 2 outputs must not overwrite the Node 1 input")
    if _same_path(args.output_json, args.output_csv):
        parser.error("--output-json and --output-csv must be different paths")

    try:
        source = _load_json(args.input_json, "Node 1 input")
        eligible = _validate_source_document(source, catalog)
    except ValueError as exc:
        parser.error(str(exc))

    existing = None
    if args.resume and args.output_json.exists():
        try:
            existing = _load_json(args.output_json, "Node 2 resume output")
        except ValueError as exc:
            parser.error(str(exc))
    elif args.resume and args.output_csv.exists():
        parser.error("Cannot resume from CSV alone; the Node 2 JSON checkpoint is missing")
    elif not args.resume and not args.overwrite and not args.dry_run:
        conflicts = [str(path) for path in (args.output_json, args.output_csv) if path.exists()]
        if conflicts:
            parser.error("Output exists; use --resume or --overwrite: " + ", ".join(conflicts))

    if existing is not None and not isinstance(existing.get("scope"), dict):
        parser.error("Node 2 resume output scope must be an object")
    output_format = args.format or (
        existing["scope"].get("output_format") if existing else "html"
    )
    if output_format not in ("html", "report"):
        parser.error("Resume output has an invalid format")

    try:
        document = (
            _new_document(source, args.input_json, output_format)
            if existing is None
            else _validate_resume_document(
                existing, source, args.input_json, output_format, args.format is not None
            )
        )
    except ValueError as exc:
        parser.error(str(exc))

    selected = _select_sources(
        eligible,
        role=args.role,
        industry=args.industry,
        jtbd=args.jtbd,
        tag_set_ids=set(args.tag_set_id),
    )
    if not selected:
        parser.error("No successful Node 1 tag sets match the filters")

    eligible_by_id = {item["tag_set_id"]: item for item in eligible}
    by_id = {
        item["tag_set_id"]: item
        for item in document["generations"]
        if item["tag_set_id"] in eligible_by_id
        and item.get("source_fingerprint")
        == _source_fingerprint(eligible_by_id[item["tag_set_id"]])
    }
    regenerate_ids = {item["tag_set_id"] for item in selected} if args.regenerate_selected else set()
    for tag_set_id in regenerate_ids:
        by_id.pop(tag_set_id, None)
    try:
        _normalize_maintained_specs(by_id, eligible, output_format, regenerate_ids)
    except ValueError as exc:
        parser.error(str(exc))

    already_succeeded = sum(
        item["tag_set_id"] not in regenerate_ids
        and _is_current_success(by_id.get(item["tag_set_id"]), item)
        for item in selected
    )
    candidates = [
        item
        for item in selected
        if item["tag_set_id"] in regenerate_ids
        or not _is_current_success(by_id.get(item["tag_set_id"]), item)
    ]
    scheduled = candidates[: args.max_batches or None]
    bounded_pause = len(scheduled) < len(candidates)
    document["source"] = _source_metadata(source, args.input_json)
    document["scope"] = _scope(source, eligible, output_format)
    document["generations"] = [by_id[key] for key in sorted(by_id)]
    document["last_run"] = {
        "started_at": _now(),
        "finished_at": "",
        "status": "dry_run" if args.dry_run else "running",
        "filters": {
            "role": args.role,
            "industry": args.industry,
            "jtbd": args.jtbd,
            "tag_set_ids": sorted(set(args.tag_set_id)),
        },
        "selected_tag_sets": len(selected),
        "already_succeeded": already_succeeded,
        "pending_before_limit": len(candidates),
        "scheduled_batches": len(scheduled),
        "max_batches": args.max_batches,
        "completed_batches": 0,
        "succeeded_batches": 0,
        "failed_batches": 0,
    }

    if args.dry_run:
        summary = _command_summary(
            document,
            args,
            eligible,
            selected,
            already_succeeded,
            scheduled,
            bounded_pause,
            dry_run=True,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    document["status"] = "running"
    _save(document, args.output_json, args.output_csv, eligible)
    _log(
        f"generate_research_prompt: selected={len(selected)} "
        f"already_succeeded={already_succeeded} scheduled={len(scheduled)} "
        f"remaining_after_limit={len(candidates) - len(scheduled)} workers={args.workers}"
    )

    if not scheduled:
        _finish_document(document, eligible, paused=bounded_pause)
        document["last_run"].update(
            {
                "finished_at": _now(),
                "status": document["status"],
            }
        )
        _save(document, args.output_json, args.output_csv, eligible)
        print(
            json.dumps(
                _command_summary(
                    document,
                    args,
                    eligible,
                    selected,
                    already_succeeded,
                    scheduled,
                    bounded_pause,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    apply_env_file_to_process(args.env_file)
    openai_settings = OpenAISettings.from_env(merged_env(args.env_file))
    local = threading.local()

    def get_model():
        if not hasattr(local, "model"):
            local.model = create_chat_model(openai_settings)
        return local.model

    def generate(source_generation: dict[str, Any]) -> dict[str, Any]:
        try:
            specs, attempts = generate_research_prompt_specs(
                source_generation, output_format, get_model
            )
            return _completed_record(source_generation, specs, attempts, output_format)
        except GenerationError as exc:
            return _failed_record(source_generation, exc.errors, output_format)
        except Exception as exc:  # noqa: BLE001 - model/provider boundary
            return _failed_record(
                source_generation,
                [f"Research prompt generation failed ({type(exc).__name__})."],
                output_format,
            )

    completed = succeeded_this_run = failed_this_run = 0
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=args.workers)
    futures = {executor.submit(generate, item): item for item in scheduled}
    interrupted = False
    second_interrupt = False
    handled = set()

    def commit(future) -> None:
        nonlocal completed, succeeded_this_run, failed_this_run
        source_generation = futures[future]
        record = future.result()
        handled.add(future)
        by_id[record["tag_set_id"]] = record
        completed += 1
        if record["status"] == "succeeded":
            succeeded_this_run += 1
        else:
            failed_this_run += 1
        document["generations"] = [by_id[key] for key in sorted(by_id)]
        document["last_run"].update(
            {
                "completed_batches": completed,
                "succeeded_batches": succeeded_this_run,
                "failed_batches": failed_this_run,
            }
        )
        _save(document, args.output_json, args.output_csv, eligible)
        generated_rows = document["progress"]["generated_rows"]
        _log(
            _progress_line(
                total=len(selected),
                already_succeeded=already_succeeded,
                completed=completed,
                succeeded_this_run=succeeded_this_run,
                failed_this_run=failed_this_run,
                generated_rows=generated_rows,
                elapsed_seconds=time.monotonic() - started,
                current_id=source_generation["tag_set_id"],
                current_status=record["status"],
                current_error=(record.get("errors") or [None])[0],
            )
        )

    try:
        for future in as_completed(futures):
            commit(future)
    except KeyboardInterrupt:
        interrupted = True
        document["status"] = "paused"
        document["last_run"]["status"] = "stopping"
        _save(document, args.output_json, args.output_csv, eligible)
        for future in futures:
            if future in handled:
                continue
            future.cancel()
        remaining = [
            future for future in futures if future not in handled and not future.cancelled()
        ]
        _log(
            "Stop requested; queued batches were cancelled. Waiting for "
            f"{len(remaining)} in-flight batch(es) so their results can be checkpointed."
        )
        try:
            for future in as_completed(remaining):
                commit(future)
        except KeyboardInterrupt:
            second_interrupt = True
            _log("Second stop requested; leaving after the latest completed checkpoint.")
    finally:
        executor.shutdown(wait=not second_interrupt, cancel_futures=interrupted)

    paused = interrupted or bounded_pause
    _finish_document(document, eligible, paused=paused)
    document["last_run"].update(
        {
            "finished_at": _now(),
            "status": document["status"],
            "completed_batches": completed,
            "succeeded_batches": succeeded_this_run,
            "failed_batches": failed_this_run,
        }
    )
    _save(document, args.output_json, args.output_csv, eligible)
    summary = _command_summary(
        document,
        args,
        eligible,
        selected,
        already_succeeded,
        scheduled,
        bounded_pause,
        interrupted=interrupted,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if interrupted:
        return 130
    return 1 if failed_this_run else 0


def _audience_values(catalog: dict[str, Any], key: str) -> list[str]:
    return [row["value"] for row in catalog["audience"][key]]


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = parse_brief_response(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise BatchFileError(f"Cannot read {label} {path} ({type(exc).__name__}).") from exc
    if not isinstance(value, dict):
        raise BatchFileError(f"{label} must contain a JSON object")
    return value


def _validate_source_document(
    document: dict[str, Any], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    if document.get("workflow_version") != NODE1_VERSION:
        raise BatchFileError(f"Input must use {NODE1_VERSION}")
    if document.get("stage") != "generate_topic":
        raise BatchFileError("Input stage must be generate_topic")
    if document.get("taxonomy_version") != catalog["taxonomy_version"]:
        raise BatchFileError("Node 1 input uses a different taxonomy version")
    if not isinstance(document.get("created_at"), str) or not document["created_at"]:
        raise BatchFileError("Node 1 input created_at is required")
    generations = document.get("generations")
    if not isinstance(generations, list):
        raise BatchFileError("Node 1 input generations must be an array")

    eligible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, generation in enumerate(generations):
        if not isinstance(generation, dict):
            raise BatchFileError(f"generations[{index}] must be an object")
        if generation.get("status") != "succeeded":
            continue
        tag_set_id = generation.get("tag_set_id")
        if not isinstance(tag_set_id, str) or not tag_set_id:
            raise BatchFileError(f"generations[{index}].tag_set_id is required")
        if tag_set_id in seen:
            raise BatchFileError(f"Duplicate successful tag_set_id: {tag_set_id}")
        seen.add(tag_set_id)
        if generation.get("schema_version") != SCHEMA_VERSION:
            raise BatchFileError(f"{tag_set_id}: unsupported generation schema_version")
        if generation.get("taxonomy_version") != catalog["taxonomy_version"]:
            raise BatchFileError(f"{tag_set_id}: generation taxonomy_version is inconsistent")
        try:
            UUID(generation.get("generation_id", ""))
        except (ValueError, TypeError, AttributeError):
            raise BatchFileError(f"{tag_set_id}: generation_id must be a UUID") from None
        try:
            datetime.fromisoformat(generation["generated_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise BatchFileError(f"{tag_set_id}: generated_at must be an ISO date-time") from None
        request = generation.get("input")
        if not isinstance(request, dict):
            raise BatchFileError(f"{tag_set_id}: input must be an object")
        audience, tag_bundle, request_errors = validate_profile_request(request)
        if request_errors:
            raise BatchFileError(
                f"{tag_set_id}: invalid Node 1 input: {'; '.join(request_errors)}"
            )
        if tag_set_id != profile_tag_set_id(audience, tag_bundle):
            raise BatchFileError(f"{tag_set_id}: tag_set_id does not match audience and tags")
        briefs = generation.get("briefs")
        count = request.get("count")
        if not isinstance(briefs, list) or not all(isinstance(brief, dict) for brief in briefs):
            raise BatchFileError(f"{tag_set_id}: briefs must be an array of objects")
        model_briefs = [{key: value for key, value in brief.items() if key != "brief_id"} for brief in briefs]
        errors = validate_profile_briefs(
            {"briefs": model_briefs}, catalog, count, audience, tag_bundle
        )
        if errors:
            raise BatchFileError(
                f"{tag_set_id}: invalid Node 1 briefs: {'; '.join(errors[:5])}"
            )
        brief_ids = [brief.get("brief_id") for brief in briefs]
        if any(not isinstance(value, str) or not value for value in brief_ids):
            raise BatchFileError(f"{tag_set_id}: every brief_id must be a non-empty string")
        if len(set(brief_ids)) != len(brief_ids):
            raise BatchFileError(f"{tag_set_id}: brief_id values must be unique")
        if generation.get("errors") != []:
            raise BatchFileError(f"{tag_set_id}: successful generation must have no errors")
        eligible.append(generation)
    return sorted(eligible, key=lambda item: item["tag_set_id"])


def _source_dataset_id(source: dict[str, Any]) -> str:
    identity = {
        "workflow_version": source.get("workflow_version"),
        "created_at": source.get("created_at"),
        "taxonomy_version": source.get("taxonomy_version"),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _source_fingerprint(generation: dict[str, Any]) -> str:
    content = {
        "schema_version": generation.get("schema_version"),
        "taxonomy_version": generation.get("taxonomy_version"),
        "tag_set_id": generation.get("tag_set_id"),
        "generation_id": generation.get("generation_id"),
        "input": generation.get("input"),
        "briefs": generation.get("briefs"),
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_metadata(source: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "dataset_id": _source_dataset_id(source),
        "json_path": str(path.resolve()),
        "workflow_version": source["workflow_version"],
        "created_at": source["created_at"],
        "updated_at": source.get("updated_at", ""),
    }


def _scope(
    source: dict[str, Any], eligible: list[dict[str, Any]], output_format: str
) -> dict[str, Any]:
    generations = source["generations"]
    return {
        "source_tag_sets": len(generations),
        "source_successful_tag_sets": len(eligible),
        "source_failed_tag_sets": sum(item.get("status") != "succeeded" for item in generations),
        "source_successful_rows": sum(len(item["briefs"]) for item in eligible),
        "output_format": output_format,
        "language_values": sorted({item["input"]["language"] for item in eligible}),
    }


def _new_document(
    source: dict[str, Any], source_path: Path, output_format: str
) -> dict[str, Any]:
    now = _now()
    return {
        "workflow_version": WORKFLOW_VERSION,
        "stage": "generate_research_prompt",
        "status": "paused",
        "created_at": now,
        "updated_at": now,
        "taxonomy_version": source["taxonomy_version"],
        "source": _source_metadata(source, source_path),
        "scope": _scope(source, [], output_format),
        "progress": {},
        "last_run": {},
        "generations": [],
    }


def _validate_resume_document(
    document: dict[str, Any],
    source: dict[str, Any],
    source_path: Path,
    output_format: str,
    format_was_explicit: bool,
) -> dict[str, Any]:
    if document.get("workflow_version") != WORKFLOW_VERSION:
        raise BatchFileError(f"Resume output must use {WORKFLOW_VERSION}")
    if document.get("stage") != "generate_research_prompt":
        raise BatchFileError("Resume output stage must be generate_research_prompt")
    if document.get("taxonomy_version") != source["taxonomy_version"]:
        raise BatchFileError("Resume output and Node 1 input use different taxonomy versions")
    metadata = document.get("source")
    if not isinstance(metadata, dict) or metadata.get("dataset_id") != _source_dataset_id(source):
        raise BatchFileError(
            "Resume output belongs to a different Node 1 dataset; use --overwrite"
        )
    old_format = (document.get("scope") or {}).get("output_format")
    if old_format != output_format:
        detail = "explicit --format" if format_was_explicit else "saved format"
        raise BatchFileError(f"{detail} does not match the Node 2 resume output")
    generations = document.get("generations")
    if not isinstance(generations, list):
        raise BatchFileError("Resume output generations must be an array")
    seen: set[str] = set()
    for index, record in enumerate(generations):
        if not isinstance(record, dict):
            raise BatchFileError(f"Resume generations[{index}] must be an object")
        tag_set_id = record.get("tag_set_id")
        if not isinstance(tag_set_id, str) or not tag_set_id or tag_set_id in seen:
            raise BatchFileError("Resume output has a missing or duplicate tag_set_id")
        seen.add(tag_set_id)
        if record.get("status") not in ("succeeded", "failed"):
            raise BatchFileError(f"{tag_set_id}: resume status must be succeeded or failed")
    document["source"] = _source_metadata(source, source_path)
    return document


def _select_sources(
    generations: Iterable[dict[str, Any]],
    *,
    role: str | None,
    industry: str | None,
    jtbd: str | None,
    tag_set_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        item
        for item in generations
        if (role is None or item["input"]["audience"]["role"] == role)
        and (industry is None or item["input"]["audience"]["industry"] == industry)
        and (jtbd is None or item["input"]["audience"]["jtbd"] == jtbd)
        and (not tag_set_ids or item["tag_set_id"] in tag_set_ids)
    ]


def _normalize_maintained_specs(
    by_id: dict[str, dict[str, Any]],
    selected: list[dict[str, Any]],
    output_format: str,
    regenerate_ids: set[str],
) -> None:
    """Rebuild prompt text from editable structured fields without another model call."""
    for source in selected:
        tag_set_id = source["tag_set_id"]
        record = by_id.get(tag_set_id)
        if (
            tag_set_id in regenerate_ids
            or not _is_current_success(record, source)
            or record is None
        ):
            continue
        specs = record.get("task_specs")
        if not isinstance(specs, list):
            raise BatchFileError(f"{tag_set_id}: successful resume record has no task_specs")
        payload = {
            "research_prompts": [
                {
                    key: spec.get(key)
                    for key in ("brief_id", "content_category", "research_instructions")
                }
                for spec in specs
                if isinstance(spec, dict)
            ]
        }
        errors = validate_research_prompts(payload, source["briefs"])
        if errors:
            raise BatchFileError(
                f"{tag_set_id}: maintained Node 2 fields are invalid: {'; '.join(errors[:5])}. "
                "Fix content_category/research_instructions or use --regenerate-selected."
            )
        summaries = {item["brief_id"]: item for item in payload["research_prompts"]}
        record.update(
            {
                "source_generation_id": source["generation_id"],
                "source_fingerprint": _source_fingerprint(source),
                "input": source["input"],
                "briefs": source["briefs"],
                "format": output_format,
                "errors": [],
            }
        )
        record["task_specs"] = [
            build_task_spec(
                brief,
                summaries[brief["brief_id"]],
                source["input"]["language"],
                output_format,
            )
            for brief in source["briefs"]
        ]


def _is_current_success(
    record: dict[str, Any] | None, source_generation: dict[str, Any]
) -> bool:
    return bool(
        record
        and record.get("status") == "succeeded"
        and record.get("source_fingerprint") == _source_fingerprint(source_generation)
    )


def _completed_record(
    source: dict[str, Any],
    specs: list[dict[str, Any]],
    attempts: int,
    output_format: str,
) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "tag_set_id": source["tag_set_id"],
        "source_generation_id": source["generation_id"],
        "source_fingerprint": _source_fingerprint(source),
        "input": source["input"],
        "briefs": source["briefs"],
        "format": output_format,
        "research_prompt_attempts": attempts,
        "research_prompt_generated_at": _now(),
        "task_specs": specs,
        "errors": [],
    }


def _failed_record(
    source: dict[str, Any], errors: list[str], output_format: str
) -> dict[str, Any]:
    return {
        "status": "failed",
        "tag_set_id": source["tag_set_id"],
        "source_generation_id": source["generation_id"],
        "source_fingerprint": _source_fingerprint(source),
        "input": source["input"],
        "briefs": source["briefs"],
        "format": output_format,
        "research_prompt_attempts": None,
        "research_prompt_generated_at": _now(),
        "task_specs": [],
        "errors": [str(error)[:2000] for error in errors] or ["Unknown generation error."],
    }


def _update_progress(
    document: dict[str, Any], eligible: list[dict[str, Any]]
) -> dict[str, int]:
    by_id = {item["tag_set_id"]: item for item in document["generations"]}
    succeeded = failed = rows = 0
    for source in eligible:
        record = by_id.get(source["tag_set_id"])
        if not record or record.get("source_fingerprint") != _source_fingerprint(source):
            continue
        if record.get("status") == "succeeded":
            succeeded += 1
            rows += len(record.get("task_specs") or [])
        elif record.get("status") == "failed":
            failed += 1
    progress = {
        "eligible_tag_sets": len(eligible),
        "succeeded_tag_sets": succeeded,
        "failed_tag_sets": failed,
        "pending_tag_sets": len(eligible) - succeeded - failed,
        "generated_rows": rows,
    }
    document["progress"] = progress
    document["updated_at"] = _now()
    return progress


def _finish_document(
    document: dict[str, Any], eligible: list[dict[str, Any]], *, paused: bool
) -> None:
    progress = _update_progress(document, eligible)
    if paused or progress["pending_tag_sets"]:
        document["status"] = "paused"
    elif progress["failed_tag_sets"]:
        document["status"] = "failed"
    else:
        document["status"] = "succeeded"


def _save(
    document: dict[str, Any],
    json_path: Path,
    csv_path: Path,
    eligible: list[dict[str, Any]],
) -> None:
    _update_progress(document, eligible)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_name(json_path.name + ".tmp")
    json_tmp.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(json_tmp, json_path)
    csv_tmp = csv_path.with_name(csv_path.name + ".tmp")
    with csv_tmp.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_rows(document, eligible))
    os.replace(csv_tmp, csv_path)


def _rows(
    document: dict[str, Any], eligible: list[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    records = {item["tag_set_id"]: item for item in document["generations"]}
    row_no = 0
    for source in eligible:
        record = records.get(source["tag_set_id"])
        if not record or record.get("source_fingerprint") != _source_fingerprint(source):
            continue
        specs = {item["brief_id"]: item for item in record.get("task_specs") or []}
        audience = source["input"]["audience"]
        for case_no, brief in enumerate(source["briefs"], 1):
            row_no += 1
            spec = specs.get(brief["brief_id"], {})
            tags = brief["tags"]
            classification = brief["classification"]
            yield {
                "row_no": row_no,
                "triple_id": triple_id(audience),
                "tag_set_id": source["tag_set_id"],
                "case_no": case_no,
                **audience,
                "question": brief["title"],
                "description": brief["description"],
                "topic_theme": tags["topic_theme"],
                "question_intent": tags["question_intent"],
                "scope_level": tags["scope_level"],
                "role_perspective": tags["role_perspective"],
                "industry_segment": tags["industry_segment"] or "",
                "jtbd_task": tags["jtbd_task"],
                "desired_output": tags["desired_output"],
                "entities": _json_cell(brief["entities"]),
                "keywords": _json_cell(brief["keywords"]),
                "classification_rationale": classification["rationale"],
                "industry_status": classification["industry_status"],
                "assumptions": _json_cell(brief["assumptions"]),
                "content_category": spec.get("content_category", ""),
                "research_instructions": spec.get("research_instructions", ""),
                "generated_prompt": spec.get("generated_prompt", ""),
                "format": record.get("format", ""),
                "research_prompt_status": record["status"],
                "research_prompt_errors": _json_cell(record.get("errors") or []),
                "research_prompt_attempts": record.get("research_prompt_attempts", 0),
                "execution_status": "not_started",
                "session_url": "",
                "share_url": "",
                "brief_id": brief["brief_id"],
                "source_generation_id": source["generation_id"],
                "taxonomy_version": source["taxonomy_version"],
                "topic_generated_at": source["generated_at"],
                "research_prompt_generated_at": record["research_prompt_generated_at"],
            }


def _command_summary(
    document: dict[str, Any],
    args: argparse.Namespace,
    eligible: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    already_succeeded: int,
    scheduled: list[dict[str, Any]],
    bounded_pause: bool,
    *,
    dry_run: bool = False,
    interrupted: bool = False,
) -> dict[str, Any]:
    progress = _update_progress(document, eligible)
    return {
        "node": "generate_research_prompt",
        "status": "dry_run" if dry_run else document["status"],
        "source_json": str(args.input_json),
        "output_json": str(args.output_json),
        "output_csv": str(args.output_csv),
        "format": document["scope"]["output_format"],
        "source_successful_tag_sets": len(eligible),
        "selected_tag_sets": len(selected),
        "already_succeeded": already_succeeded,
        "scheduled_batches": len(scheduled),
        "bounded_pause": bounded_pause,
        "interrupted": interrupted,
        **progress,
        "eureka_calls": 0,
    }


def _progress_line(
    *,
    total: int,
    already_succeeded: int,
    completed: int,
    succeeded_this_run: int,
    failed_this_run: int,
    generated_rows: int,
    elapsed_seconds: float,
    current_id: str,
    current_status: str,
    current_error: str | None,
) -> str:
    processed = already_succeeded + completed
    percent = 100 * processed / total if total else 100.0
    remaining = max(total - processed, 0)
    eta = elapsed_seconds * remaining / completed if completed else None
    line = (
        f"[{processed}/{total} | {percent:5.1f}%] "
        f"succeeded={already_succeeded + succeeded_this_run} failed={failed_this_run} "
        f"rows={generated_rows} "
        f"elapsed={_duration(elapsed_seconds)} eta={_duration(eta)} "
        f"{current_id}: {current_status}"
    )
    return f"{line} | {current_error}" if current_error else line


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _same_path(left: Path, right: Path) -> bool:
    return left.expanduser().resolve() == right.expanduser().resolve()


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
