"""Validate saved or manually edited results at generation/execution boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from .brief_schema import LANGUAGES, MAX_BRIEFS, SCHEMA_VERSION, load_brief_catalog, validate_briefs
from .summary_generation import GenerationError, build_task_spec, validate_summaries


def validate_generation_result(value: Any, stage: str) -> None:
    if not isinstance(value, dict):
        raise GenerationError(stage, ["generation_result must be an object."])
    errors = []
    if value.get("status") != "succeeded" or value.get("errors") != []:
        errors.append("Only a successful generation result can be continued.")
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unsupported generation schema version.")
    if value.get("taxonomy_version") != load_brief_catalog()["taxonomy_version"]:
        errors.append("Unsupported taxonomy version.")
    if not _is_uuid(value.get("generation_id")):
        errors.append("generation_id must be a UUID.")
    try:
        datetime.fromisoformat(value["generated_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append("generated_at must be an ISO date-time.")

    request = value.get("input")
    if not isinstance(request, dict):
        errors.append("generation input must be an object.")
        request = {}
    idea, count = request.get("idea"), request.get("count")
    if not isinstance(idea, str) or not idea.strip() or len(idea) > 8000:
        errors.append("generation input.idea must contain 1..8000 characters.")
    if request.get("language") not in LANGUAGES:
        errors.append("generation input.language must be zh-CN or en.")
    if type(count) is not int or not 1 <= count <= MAX_BRIEFS:
        errors.append(f"generation input.count must be an integer in 1..{MAX_BRIEFS}.")

    briefs = value.get("briefs")
    if not isinstance(briefs, list) or not briefs or not all(isinstance(b, dict) for b in briefs):
        errors.append("generation briefs must be a non-empty array of objects.")
    else:
        ids = [b.get("brief_id") for b in briefs]
        if not all(_is_uuid(key) for key in ids) or len(set(map(str, ids))) != len(ids):
            errors.append("brief_id values must be unique UUIDs.")
        errors.extend(
            validate_briefs(
                {"briefs": [{k: v for k, v in b.items() if k != "brief_id"} for b in briefs]},
                count=count if type(count) is int else None,
            )
        )
    if errors:
        raise GenerationError(stage, errors)


def validate_task_specs(generation: dict, specs: Any, output_format: Any, stage: str) -> None:
    if output_format not in ("html", "report"):
        raise GenerationError(stage, ["format must be html or report."])
    if not isinstance(specs, list) or not all(isinstance(spec, dict) for spec in specs):
        raise GenerationError(stage, ["task_specs must be an array of objects."])
    summaries = {
        "summaries": [
            {
                key: spec.get(key)
                for key in ("brief_id", "content_category", "research_instructions")
            }
            for spec in specs
        ]
    }
    errors = validate_summaries(summaries, generation["briefs"])
    if not errors:
        for brief, spec in zip(generation["briefs"], specs):
            if spec != build_task_spec(brief, spec, generation["input"]["language"], output_format):
                errors.append(
                    "Task prompt or metadata does not match its brief, language, format or order. "
                    "To revise a topic, clear task_specs and regenerate_summary."
                )
    if errors:
        raise GenerationError(stage, errors)


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False
