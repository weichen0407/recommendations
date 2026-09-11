"""Batch node-one generation for fixed audience and multidimensional tag sets."""

from __future__ import annotations

import argparse
import csv
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .brief_schema import SCHEMA_VERSION, load_brief_catalog
from .config import apply_env_file_to_process
from .profile_topic_generation import all_profile_triples, triple_id

DEFAULT_JSON = Path("outputs/profile_topics/node1_topics_v4.json")
DEFAULT_CSV = Path("outputs/profile_topics/node1_topics_v4.csv")

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
    "summary",
    "content_category",
    "generated_prompt",
    "execution_status",
    "session_url",
    "share_url",
    "brief_id",
    "generation_id",
    "taxonomy_version",
    "generated_at",
]


def main(argv: list[str] | None = None) -> int:
    catalog = load_brief_catalog()
    parser = argparse.ArgumentParser(
        description="Node 1: generate question variants for fixed multidimensional tag sets."
    )
    parser.add_argument(
        "--cases-per-tag-set",
        "--cases-per-triple",
        dest="cases_per_tag_set",
        type=int,
        choices=range(1, 11),
        default=10,
    )
    parser.add_argument("--language", choices=["zh-CN", "en"], default="zh-CN")
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=4)
    parser.add_argument("--role", choices=_values(catalog, "role"))
    parser.add_argument("--industry", choices=_values(catalog, "industry"))
    parser.add_argument("--jtbd", choices=_values(catalog, "jtbd"))
    parser.add_argument(
        "--role-perspective", choices=_catalog_values(catalog, "role_perspectives")
    )
    parser.add_argument(
        "--industry-segment", choices=_catalog_values(catalog, "industry_segments")
    )
    parser.add_argument("--jtbd-task", choices=_catalog_values(catalog, "jtbd_tasks"))
    parser.add_argument(
        "--desired-output", choices=_catalog_values(catalog, "desired_outputs")
    )
    parser.add_argument("--topic-theme", choices=_catalog_values(catalog, "topic_themes"))
    parser.add_argument(
        "--question-intent", choices=_catalog_values(catalog, "question_intents")
    )
    parser.add_argument("--scope-level", choices=_catalog_values(catalog, "scope_levels"))
    parser.add_argument("--limit-triples", type=int, default=0)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--resume", action="store_true", help="Skip successful triples in JSON.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="List scope without calling the model."
    )
    args = parser.parse_args(argv)
    if args.resume and args.overwrite:
        parser.error("--resume and --overwrite cannot be combined")
    if args.limit_triples < 0:
        parser.error("--limit-triples must be non-negative")
    tag_overrides = _tag_overrides(args)

    triples = _select_triples(catalog, args.role, args.industry, args.jtbd)
    if args.limit_triples:
        triples = triples[: args.limit_triples]
    if not triples:
        parser.error("No allowed triples match the filters")

    existing = _load_existing(args.output_json) if args.resume else None
    if not args.resume and not args.overwrite:
        conflicts = [str(path) for path in (args.output_json, args.output_csv) if path.exists()]
        if conflicts:
            parser.error("Output exists; use --resume or --overwrite: " + ", ".join(conflicts))
    document = (
        _new_document(catalog, triples, args, tag_overrides) if existing is None else existing
    )
    _validate_resume(document, catalog, args, tag_overrides)
    successful = {
        triple_id(item["input"]["audience"])
        for item in document["generations"]
        if item.get("status") == "succeeded"
    }
    pending = [audience for audience in triples if triple_id(audience) not in successful]
    document["scope"]["selected_triples"] = len(triples)
    document["scope"]["expected_rows"] = len(triples) * args.cases_per_tag_set
    _save(document, args.output_json, args.output_csv)

    print(
        json.dumps(
            {
                "node": "generate_topic",
                "triples": len(triples),
                "cases_per_tag_set": args.cases_per_tag_set,
                "tag_overrides": tag_overrides,
                "expected_rows": len(triples) * args.cases_per_tag_set,
                "already_succeeded": len(triples) - len(pending),
                "pending": len(pending),
                "model_calls": 0 if args.dry_run else len(pending),
                "output_json": str(args.output_json),
                "output_csv": str(args.output_csv),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if args.dry_run or not pending:
        return 0

    apply_env_file_to_process(args.env_file)
    local = threading.local()

    def generate(audience):
        if not hasattr(local, "graph"):
            from .brief_graph import build_brief_graph

            local.graph = build_brief_graph(env_file=args.env_file)
        return local.graph.invoke(
            {
                "audience": audience,
                "tag_overrides": tag_overrides,
                "language": args.language,
                "count": args.cases_per_tag_set,
            },
            config={"run_name": "profile_topic_node1", "tags": ["node1", triple_id(audience)]},
        )["result"]

    by_id = {triple_id(item["input"]["audience"]): item for item in document["generations"]}
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(generate, audience): audience for audience in pending}
        for future in as_completed(futures):
            audience = futures[future]
            try:
                generation = future.result()
            except Exception as exc:  # noqa: BLE001 - graph/provider boundary
                generation = _failed_generation(audience, args, exc)
            by_id[triple_id(audience)] = generation
            completed += 1
            document["generations"] = [by_id[key] for key in sorted(by_id)]
            _update_progress(document)
            _save(document, args.output_json, args.output_csv)
            print(
                f"[{completed}/{len(pending)}] {triple_id(audience)}: {generation['status']}",
                flush=True,
            )
    return 0 if document["progress"]["failed_triples"] == 0 else 1


def _values(catalog: dict[str, Any], dimension: str) -> list[str]:
    return [row["value"] for row in catalog["audience"][dimension]]


def _catalog_values(catalog: dict[str, Any], key: str) -> list[str]:
    return [row["value"] for row in catalog[key]]


def _tag_overrides(args) -> dict[str, Any]:
    values = {
        "role_perspective": args.role_perspective,
        "industry_segment": args.industry_segment,
        "jtbd_task": args.jtbd_task,
        "desired_output": args.desired_output,
        "topic_theme": args.topic_theme,
        "question_intent": args.question_intent,
        "scope_level": args.scope_level,
    }
    result = {key: value for key, value in values.items() if value is not None}
    if "scope_level" not in result and result.get("industry_segment"):
        result["scope_level"] = "industry_segment"
    return result


def _select_triples(catalog, role, industry, jtbd):
    return [
        audience
        for audience in all_profile_triples(catalog)
        if (role is None or audience["role"] == role)
        and (industry is None or audience["industry"] == industry)
        and (jtbd is None or audience["jtbd"] == jtbd)
    ]


def _new_document(catalog, triples, args, tag_overrides):
    return {
        "workflow_version": "profile-topic-node1/4.0.0",
        "stage": "generate_topic",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": catalog["taxonomy_version"],
        "scope": {
            "selection": "role_allowed_jtbd × selected industries",
            "selected_triples": len(triples),
            "cases_per_tag_set": args.cases_per_tag_set,
            "tag_overrides": tag_overrides,
            "expected_rows": len(triples) * args.cases_per_tag_set,
            "language": args.language,
        },
        "progress": {},
        "generations": [],
    }


def _load_existing(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot resume {path} ({type(exc).__name__}).") from exc
    if not isinstance(value, dict):
        raise SystemExit("Resume JSON must contain an object.")
    return value


def _validate_resume(document, catalog, args, tag_overrides):
    if document.get("workflow_version") != "profile-topic-node1/4.0.0":
        raise SystemExit("Unsupported node-one output version.")
    if document.get("taxonomy_version") != catalog["taxonomy_version"]:
        raise SystemExit("Node-one output uses a different taxonomy version.")
    scope = document.get("scope") or {}
    if scope.get("cases_per_tag_set") != args.cases_per_tag_set:
        raise SystemExit("--cases-per-tag-set must match the resume file.")
    if scope.get("language") != args.language:
        raise SystemExit("--language must match the resume file.")
    if scope.get("tag_overrides") != tag_overrides:
        raise SystemExit("Tag enum selections must match the resume file.")


def _failed_generation(audience, args, exc):
    return {
        "status": "failed",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": load_brief_catalog()["taxonomy_version"],
        "generation_id": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "audience": audience,
            "tag_overrides": _tag_overrides(args),
            "language": args.language,
            "count": args.cases_per_tag_set,
        },
        "attempts": 0,
        "briefs": [],
        "errors": [f"Graph execution failed ({type(exc).__name__})."],
    }


def _update_progress(document):
    generations = document["generations"]
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    document["progress"] = {
        "successful_triples": sum(item.get("status") == "succeeded" for item in generations),
        "failed_triples": sum(item.get("status") != "succeeded" for item in generations),
        "generated_rows": sum(len(item.get("briefs") or []) for item in generations),
    }


def _save(document: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    _update_progress(document)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    json_tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(json_tmp, json_path)
    csv_tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with csv_tmp.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_rows(document))
    os.replace(csv_tmp, csv_path)


def _rows(document):
    row_no = 0
    for generation in document["generations"]:
        audience = generation["input"]["audience"]
        for case_no, brief in enumerate(generation.get("briefs") or [], 1):
            row_no += 1
            tags, classification = brief["tags"], brief["classification"]
            yield {
                "row_no": row_no,
                "triple_id": triple_id(audience),
                "tag_set_id": generation["tag_set_id"],
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
                "summary": "",
                "content_category": "",
                "generated_prompt": "",
                "execution_status": "not_started",
                "session_url": "",
                "share_url": "",
                "brief_id": brief["brief_id"],
                "generation_id": generation["generation_id"],
                "taxonomy_version": generation["taxonomy_version"],
                "generated_at": generation["generated_at"],
            }


def _json_cell(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
