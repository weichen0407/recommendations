"""Stage-one vocabulary, JSON contract, and deterministic combination checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
CATALOG_PATH = Path(__file__).parent / "data" / "content_brief_catalog.json"
LANGUAGES = ("zh-CN", "en")
MAX_BRIEFS = 10


def load_brief_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _string(max_length: int = 1000) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": max_length}


def _enum(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "string", "enum": [row["value"] for row in rows]}


def _array(items: dict[str, Any], minimum: int, maximum: int) -> dict[str, Any]:
    return {
        "type": "array",
        "items": items,
        "minItems": minimum,
        "maxItems": maximum,
        "uniqueItems": True,
    }


def build_brief_schema(
    catalog: dict[str, Any] | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """Model response schema. Cross-field constraints are checked by validate_briefs."""
    catalog = catalog if catalog is not None else load_brief_catalog()
    if count is not None and (type(count) is not int or not 1 <= count <= MAX_BRIEFS):
        raise ValueError(f"count must be an integer between 1 and {MAX_BRIEFS}")
    segment = _enum(catalog["industry_segments"])
    segment["type"] = ["string", "null"]
    segment["enum"] = [*segment["enum"], None]
    brief = _object(
        {
            "title": _string(160),
            "description": _string(1600),
            "entities": _array(_string(200), 0, 10),
            "keywords": _array(_string(100), 1, 12),
            "audience": _object({key: _enum(rows) for key, rows in catalog["audience"].items()}),
            "tags": _object(
                {
                    "role_perspective": _enum(catalog["role_perspectives"]),
                    "industry_segment": segment,
                    "technology_object": _array(_enum(catalog["technology_objects"]), 0, 2),
                    "jtbd_task": _enum(catalog["jtbd_tasks"]),
                    "desired_output": _enum(catalog["desired_outputs"]),
                }
            ),
            "classification": _object(
                {
                    "rationale": _string(1000),
                    "industry_status": {
                        "type": "string",
                        "enum": catalog["classification_statuses"]["industry"],
                    },
                    "object_status": {
                        "type": "string",
                        "enum": catalog["classification_statuses"]["objects"],
                    },
                }
            ),
            "assumptions": _array(_string(400), 0, 8),
        }
    )
    schema = _object({"briefs": _array(brief, count or 1, count or MAX_BRIEFS)})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Operations content brief model response",
        "description": (
            "Stage 1 only. Audience labels are outputs, not user inputs. "
            "Also apply the catalog combination rules and semantic editorial review."
        ),
        **schema,
    }


def _shape_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the exact keyword subset emitted above, without an extra dependency."""
    errors: list[str] = []
    kinds = schema["type"]
    kinds = kinds if isinstance(kinds, list) else [kinds]
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "null": value is None,
    }
    if not any(matches[kind] for kind in kinds):
        return [f"{path}: expected {' or '.join(kinds)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not in the allowed enum")
    if isinstance(value, str):
        if not value.strip():
            errors.append(f"{path}: must not be blank")
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: too short")
        if len(value) > schema.get("maxLength", len(value)):
            errors.append(f"{path}: too long")
    elif isinstance(value, dict):
        properties = schema["properties"]
        for key in schema["required"]:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, item in value.items():
            if key not in properties:
                errors.append(f"{path}: unexpected field {str(key)[:80]}")
            else:
                errors.extend(_shape_errors(item, properties[key], f"{path}.{key}"))
    elif isinstance(value, list):
        if not schema["minItems"] <= len(value) <= schema["maxItems"]:
            errors.append(f"{path}: expected {schema['minItems']}..{schema['maxItems']} items")
        if schema["uniqueItems"] and any(item in value[:i] for i, item in enumerate(value)):
            errors.append(f"{path}: duplicate items")
        for i, item in enumerate(value):
            errors.extend(_shape_errors(item, schema["items"], f"{path}[{i}]"))
    return errors


def validate_briefs(
    payload: Any,
    catalog: dict[str, Any] | None = None,
    count: int | None = None,
) -> list[str]:
    catalog = catalog if catalog is not None else load_brief_catalog()
    errors = _shape_errors(payload, build_brief_schema(catalog, count))
    if errors:
        return errors
    segments = {row["value"]: row for row in catalog["industry_segments"]}
    objects = {row["value"]: row for row in catalog["technology_objects"]}
    tasks = {row["value"]: row for row in catalog["jtbd_tasks"]}
    descriptions: set[str] = set()
    for i, brief in enumerate(payload["briefs"]):
        path = f"$.briefs[{i}]"
        tags, audience, classification = brief["tags"], brief["audience"], brief["classification"]
        task = tasks[tags["jtbd_task"]]
        if task["value"] not in catalog["jtbd_allowed_tasks"][audience["jtbd"]]:
            errors.append(f"{path}: jtbd_task is incompatible with audience.jtbd")
        if tags["role_perspective"] not in task["allowed_perspectives"]:
            errors.append(f"{path}: role_perspective is incompatible with jtbd_task")
        if tags["desired_output"] not in task["allowed_outputs"]:
            errors.append(f"{path}: desired_output is incompatible with jtbd_task")
        segment = tags["industry_segment"]
        if segment is None:
            if classification["industry_status"] == "classified":
                errors.append(f"{path}: null industry_segment cannot be classified")
            if (
                tags["technology_object"]
                or classification["object_status"] != "industry_unresolved"
            ):
                errors.append(
                    f"{path}: unresolved industry requires [] objects and industry_unresolved"
                )
        else:
            if classification["industry_status"] != "classified":
                errors.append(f"{path}: non-null industry_segment requires classified status")
            if audience["industry"] != segments[segment]["entry_industry"]:
                errors.append(f"{path}: audience.industry must match industry_segment parent")
            for obj in tags["technology_object"]:
                if segment not in objects[obj]["allowed_segments"]:
                    errors.append(f"{path}: technology_object {obj} is incompatible with segment")
            expected = (
                {"classified"} if tags["technology_object"] else {"broad_scope", "not_in_catalog"}
            )
            if classification["object_status"] not in expected:
                errors.append(f"{path}: object_status is inconsistent with technology_object")
        normalized = " ".join(brief["description"].casefold().split())
        if normalized in descriptions:
            errors.append(f"{path}: duplicate description in this batch")
        descriptions.add(normalized)
    return errors


def parse_brief_response(raw: str) -> Any:
    """Accept a JSON response or a single JSON fence; reject duplicate keys and prose."""
    raw = raw.strip()
    if raw.startswith(("```json\n", "```\n")):
        if not raw.endswith("\n```"):
            raise ValueError("incomplete JSON fence")
        raw = raw.split("\n", 1)[1].rsplit("\n```", 1)[0]

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite JSON number")

    return json.loads(raw, object_pairs_hook=unique_keys, parse_constant=reject_constant)
