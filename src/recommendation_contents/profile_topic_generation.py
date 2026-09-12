"""Generate question variants from a fixed audience and multidimensional tag bundle."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .brief_generation import response_text
from .brief_schema import (
    LANGUAGES,
    MAX_BRIEFS,
    SCHEMA_VERSION,
    _shape_errors,
    build_brief_schema,
    load_brief_catalog,
    parse_brief_response,
    validate_briefs,
)
from .llm import format_llm_error

PROFILE_TAG_KEYS = (
    "role_perspective",
    "industry_segment",
    "jtbd_task",
    "desired_output",
    "topic_theme",
    "question_intent",
    "scope_level",
)

PROFILE_TOPIC_RULES = """You are an operations editor for recommended-content topics. The input
contains a fixed target audience and a fixed tag bundle. They describe who the content suits and
which topic angle it covers; they are not a personal user profile. Generate the requested number
of distinct research questions from this one fixed combination.

Requirements:
1. Every title must be a natural, specific question that ends with a question mark and can be
   displayed directly to a user.
2. Write description as one complete sentence stating the work perspective, industry scope,
   concrete task, and expected deliverable. Do not provide the answer.
3. Copy role, industry, and jtbd from the input audience exactly. Do not reclassify any value or
   replace it with other.
4. Copy the input tag_bundle exactly. Every question must share the same perspective, industry
   segment, task, deliverable, topic theme, question intent, and scope level.
5. Keep an industry scope broad when scope_level=industry. Limit the question to the selected
   segment when scope_level=industry_segment. Do not descend into a more specific product or
   project without input support.
6. Do not assume a particular product, material, component, manufacturing parameter window,
   failure symptom, experiment cohort, structural choice, or project acceptance threshold. Prefer
   industry-level questions about major applications, research trends, key fields, technical
   challenges, improvement directions, emerging areas, or concept explanations.
7. topic_theme controls the subject angle and question_intent controls the question action. You
   may vary the application context, affected stage, evidence angle, or wording, but every item
   must satisfy both fixed tags. Do not switch theme or intent merely to create variety.
8. Use entities/keywords as free text for concrete company, product, technology, material, or
   component names. These are not controlled enums and cannot replace topic_theme for stable
   aggregation.
9. Multiple questions must have real research differences and cannot be synonymous rewrites. All
   differences must remain within the fixed scope and task.
10. Do not invent company facts, market data, patent conclusions, or personal project materials.
    Put any added scenario, region, or time window in assumptions.
11. Output only the Node 1 questions and structured tags. Do not include a summary, final execution
    prompt, curl command, HTML requirement, or tool-call instruction.
12. Write title, description, rationale, and assumptions in the requested language. Keep enum keys
    exactly as their English catalog values.
13. Return only JSON that conforms to the schema, without Markdown or surrounding explanation.
"""


def validate_profile_request(
    request: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    catalog = load_brief_catalog()
    audience = request.get("audience")
    language, count = request.get("language", "zh-CN"), request.get("count", 10)
    errors = []
    if not isinstance(audience, dict) or set(audience) != {"role", "industry", "jtbd"}:
        errors.append("audience must contain exactly role, industry and jtbd")
        audience = {}
    for key in ("role", "industry", "jtbd"):
        allowed = {row["value"] for row in catalog["audience"][key]}
        if audience.get(key) not in allowed:
            errors.append(f"audience.{key} must be an allowed enum")
    role, jtbd = audience.get("role"), audience.get("jtbd")
    if role in catalog["role_allowed_jtbd"] and jtbd not in catalog["role_allowed_jtbd"][role]:
        errors.append("audience.jtbd is not enabled for audience.role")
    if language not in LANGUAGES:
        errors.append("language must be zh-CN or en")
    if type(count) is not int or not 1 <= count <= MAX_BRIEFS:
        errors.append(f"count must be an integer between 1 and {MAX_BRIEFS}")
    normalized_audience = {
        key: audience.get(key, "") for key in ("role", "industry", "jtbd")
    }
    tag_bundle: dict[str, Any] = {}
    if not errors:
        tag_bundle = default_profile_tag_bundle(catalog, normalized_audience)
        supplied = request.get("tag_bundle")
        overrides = request.get("tag_overrides")
        if supplied is not None and overrides is not None:
            errors.append("use tag_bundle or tag_overrides, not both")
        elif supplied is not None:
            if not isinstance(supplied, dict):
                errors.append("tag_bundle must be an object")
            else:
                tag_bundle = dict(supplied)
        elif overrides is not None:
            if not isinstance(overrides, dict):
                errors.append("tag_overrides must be an object")
            elif set(overrides) - set(PROFILE_TAG_KEYS):
                errors.append("tag_overrides contains unsupported fields")
            else:
                tag_bundle.update(overrides)
                _complete_tag_overrides(tag_bundle, overrides, catalog, normalized_audience)
        if not errors:
            errors.extend(_profile_tag_bundle_errors(tag_bundle, catalog, normalized_audience))
    return normalized_audience, tag_bundle, errors


def generate_profile_topics(
    request: dict[str, Any], get_model: Callable[[], Any]
) -> dict[str, Any]:
    audience, tag_bundle, errors = validate_profile_request(request)
    language, count = request.get("language", "zh-CN"), request.get("count", 10)
    catalog = load_brief_catalog()
    focused = _focused_catalog(catalog, audience, tag_bundle) if not errors else catalog
    normalized = {
        "audience": audience,
        "tag_bundle": tag_bundle,
        "language": language,
        "count": count,
    }
    raw, attempts, briefs = "", 0, []
    if not errors:
        for attempt in range(2):
            attempts += 1
            try:
                raw = response_text(
                    get_model().invoke(
                        _profile_messages(
                            normalized,
                            focused,
                            previous_response=raw if attempt else None,
                            errors=errors,
                        )
                    )
                )
            except Exception as exc:  # noqa: BLE001 - model-provider boundary
                errors = [format_llm_error(exc)]
                break
            try:
                candidate = parse_brief_response(raw)
                errors = validate_profile_briefs(
                    candidate, focused, count, audience, tag_bundle
                )
            except (ValueError, RecursionError):
                errors = ["Response must be a JSON object with unique keys."]
            if not errors:
                briefs = [{"brief_id": str(uuid4()), **brief} for brief in candidate["briefs"]]
                break
    return {
        "status": "failed" if errors else "succeeded",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": catalog["taxonomy_version"],
        "tag_set_id": profile_tag_set_id(audience, tag_bundle) if tag_bundle else "",
        "generation_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": normalized,
        "attempts": attempts,
        "briefs": briefs,
        "errors": errors,
    }


def all_profile_triples(catalog: dict[str, Any] | None = None) -> list[dict[str, str]]:
    catalog = catalog or load_brief_catalog()
    industries = [row["value"] for row in catalog["audience"]["industry"]]
    return [
        {"role": role, "industry": industry, "jtbd": jtbd}
        for role, jtbd_values in catalog["role_allowed_jtbd"].items()
        for jtbd in jtbd_values
        for industry in industries
    ]


def triple_id(audience: dict[str, str]) -> str:
    return "__".join(audience[key] for key in ("role", "industry", "jtbd"))


def profile_tag_set_id(audience: dict[str, str], tag_bundle: dict[str, Any]) -> str:
    canonical = json.dumps(tag_bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{triple_id(audience)}__{digest}"


def default_profile_tag_bundle(
    catalog: dict[str, Any], audience: dict[str, str]
) -> dict[str, Any]:
    """Choose one deterministic, broad-scope bundle when no child enums are supplied."""
    task_rows = {row["value"]: row for row in catalog["jtbd_tasks"]}
    preferred = catalog["role_preferred_perspectives"][audience["role"]]
    all_perspectives = [row["value"] for row in catalog["role_perspectives"]]
    chosen_task = None
    chosen_perspective = None
    for task_value in catalog["jtbd_allowed_tasks"][audience["jtbd"]]:
        task = task_rows[task_value]
        candidates = [p for p in preferred if p in task["allowed_perspectives"]]
        if not candidates:
            candidates = [p for p in all_perspectives if p in task["allowed_perspectives"]]
        if candidates:
            chosen_task, chosen_perspective = task, candidates[0]
            break
    if chosen_task is None or chosen_perspective is None:
        raise ValueError("No compatible task and role perspective for audience")
    theme = catalog["jtbd_allowed_topic_themes"][audience["jtbd"]][0]
    return {
        "role_perspective": chosen_perspective,
        "industry_segment": None,
        "jtbd_task": chosen_task["value"],
        "desired_output": chosen_task["allowed_outputs"][0],
        "topic_theme": theme,
        "question_intent": catalog["topic_theme_allowed_question_intents"][theme][0],
        "scope_level": "industry",
    }


def _complete_tag_overrides(
    bundle: dict[str, Any],
    overrides: dict[str, Any],
    catalog: dict[str, Any],
    audience: dict[str, str],
) -> None:
    """Fill dependent enum values after a caller overrides one parent selection."""
    tasks = {row["value"]: row for row in catalog["jtbd_tasks"]}
    task = tasks.get(bundle["jtbd_task"])
    if task is not None:
        if "desired_output" not in overrides:
            bundle["desired_output"] = task["allowed_outputs"][0]
        if (
            "role_perspective" not in overrides
            and bundle["role_perspective"] not in task["allowed_perspectives"]
        ):
            preferred = catalog["role_preferred_perspectives"][audience["role"]]
            candidates = [p for p in preferred if p in task["allowed_perspectives"]]
            if not candidates:
                candidates = list(task["allowed_perspectives"])
            if candidates:
                bundle["role_perspective"] = candidates[0]
    theme = bundle["topic_theme"]
    allowed_intents = catalog["topic_theme_allowed_question_intents"].get(theme)
    if "question_intent" not in overrides and allowed_intents:
        bundle["question_intent"] = allowed_intents[0]
    if "scope_level" not in overrides:
        bundle["scope_level"] = "industry_segment" if bundle["industry_segment"] else "industry"


def _profile_tag_bundle_errors(
    bundle: dict[str, Any], catalog: dict[str, Any], audience: dict[str, str]
) -> list[str]:
    if set(bundle) != set(PROFILE_TAG_KEYS):
        return ["tag_bundle must contain exactly " + ", ".join(PROFILE_TAG_KEYS)]
    errors: list[str] = []
    rows = {
        key: {row["value"]: row for row in catalog[key]}
        for key in (
            "role_perspectives",
            "industry_segments",
            "jtbd_tasks",
            "desired_outputs",
            "topic_themes",
            "question_intents",
            "scope_levels",
        )
    }
    scalar_fields = {
        "role_perspective": "role_perspectives",
        "jtbd_task": "jtbd_tasks",
        "desired_output": "desired_outputs",
        "topic_theme": "topic_themes",
        "question_intent": "question_intents",
        "scope_level": "scope_levels",
    }
    for field, catalog_key in scalar_fields.items():
        if bundle[field] not in rows[catalog_key]:
            errors.append(f"tag_bundle.{field} must be an allowed enum")
    segment = bundle["industry_segment"]
    if segment is not None and segment not in rows["industry_segments"]:
        errors.append("tag_bundle.industry_segment must be null or an allowed enum")
    if errors:
        return errors

    focused = _focused_catalog(catalog, audience)
    allowed_perspectives = {row["value"] for row in focused["role_perspectives"]}
    if bundle["role_perspective"] not in allowed_perspectives:
        errors.append("tag_bundle.role_perspective is incompatible with audience.role and JTBD")
    task = rows["jtbd_tasks"][bundle["jtbd_task"]]
    if task["value"] not in catalog["jtbd_allowed_tasks"][audience["jtbd"]]:
        errors.append("tag_bundle.jtbd_task is incompatible with audience.jtbd")
    if bundle["role_perspective"] not in task["allowed_perspectives"]:
        errors.append("tag_bundle.role_perspective is incompatible with jtbd_task")
    if bundle["desired_output"] not in task["allowed_outputs"]:
        errors.append("tag_bundle.desired_output is incompatible with jtbd_task")
    if segment is not None and rows["industry_segments"][segment]["entry_industry"] != audience[
        "industry"
    ]:
        errors.append("tag_bundle.industry_segment is incompatible with audience.industry")
    theme = bundle["topic_theme"]
    if theme not in catalog["jtbd_allowed_topic_themes"][audience["jtbd"]]:
        errors.append("tag_bundle.topic_theme is incompatible with audience.jtbd")
    if bundle["question_intent"] not in catalog["topic_theme_allowed_question_intents"][theme]:
        errors.append("tag_bundle.question_intent is incompatible with topic_theme")
    expected_scope = "industry_segment" if segment else "industry"
    if bundle["scope_level"] != expected_scope:
        errors.append("tag_bundle.scope_level is inconsistent with industry_segment")
    return errors


def _focused_catalog(
    catalog: dict[str, Any],
    audience: dict[str, str],
    tag_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tasks = [
        row
        for row in catalog["jtbd_tasks"]
        if row["value"] in catalog["jtbd_allowed_tasks"][audience["jtbd"]]
    ]
    task_perspectives = {p for row in tasks for p in row["allowed_perspectives"]}
    preferred = set(catalog["role_preferred_perspectives"][audience["role"]])
    perspectives = task_perspectives & preferred or task_perspectives
    outputs = {value for row in tasks for value in row["allowed_outputs"]}
    segments = [
        row for row in catalog["industry_segments"] if row["entry_industry"] == audience["industry"]
    ]
    focused = dict(catalog)
    focused["audience"] = {
        key: [row for row in catalog["audience"][key] if row["value"] == audience[key]]
        for key in ("role", "industry", "jtbd")
    }
    focused["role_perspectives"] = [
        row for row in catalog["role_perspectives"] if row["value"] in perspectives
    ]
    focused["industry_segments"] = segments
    focused["jtbd_tasks"] = tasks
    focused["desired_outputs"] = [
        row for row in catalog["desired_outputs"] if row["value"] in outputs
    ]
    focused["topic_themes"] = [
        row
        for row in catalog["topic_themes"]
        if row["value"] in catalog["jtbd_allowed_topic_themes"][audience["jtbd"]]
    ]
    focused["jtbd_allowed_topic_themes"] = {
        audience["jtbd"]: catalog["jtbd_allowed_topic_themes"][audience["jtbd"]]
    }
    allowed_intents = {
        value
        for row in focused["topic_themes"]
        for value in catalog["topic_theme_allowed_question_intents"][row["value"]]
    }
    focused["question_intents"] = [
        row for row in catalog["question_intents"] if row["value"] in allowed_intents
    ]
    focused["scope_levels"] = list(catalog["scope_levels"])
    focused["topic_theme_allowed_question_intents"] = {
        row["value"]: catalog["topic_theme_allowed_question_intents"][row["value"]]
        for row in focused["topic_themes"]
    }
    focused["role_preferred_perspectives"] = {
        audience["role"]: catalog["role_preferred_perspectives"][audience["role"]]
    }
    focused["role_allowed_jtbd"] = {audience["role"]: [audience["jtbd"]]}
    focused["jtbd_allowed_tasks"] = {
        audience["jtbd"]: catalog["jtbd_allowed_tasks"][audience["jtbd"]]
    }
    if tag_bundle is not None:
        selected = {
            "role_perspectives": {tag_bundle["role_perspective"]},
            "industry_segments": (
                {tag_bundle["industry_segment"]} if tag_bundle["industry_segment"] else set()
            ),
            "jtbd_tasks": {tag_bundle["jtbd_task"]},
            "desired_outputs": {tag_bundle["desired_output"]},
            "topic_themes": {tag_bundle["topic_theme"]},
            "question_intents": {tag_bundle["question_intent"]},
            "scope_levels": {tag_bundle["scope_level"]},
        }
        for key, values in selected.items():
            focused[key] = [row for row in focused[key] if row["value"] in values]
        focused["jtbd_allowed_topic_themes"] = {
            audience["jtbd"]: [tag_bundle["topic_theme"]]
        }
        focused["topic_theme_allowed_question_intents"] = {
            tag_bundle["topic_theme"]: [tag_bundle["question_intent"]]
        }
        focused["jtbd_allowed_tasks"] = {audience["jtbd"]: [tag_bundle["jtbd_task"]]}
    return focused


def _profile_messages(
    request: dict[str, Any],
    catalog: dict[str, Any],
    previous_response: str | None,
    errors: list[str],
) -> list[dict[str, str]]:
    compact_keys = {
        "value",
        "label_en",
        "definition",
        "boundary",
        "entry_industry",
        "allowed_perspectives",
        "allowed_outputs",
    }
    compact = {
        "role_preferred_perspectives": catalog["role_preferred_perspectives"],
        "jtbd_allowed_tasks": catalog["jtbd_allowed_tasks"],
        "topic_theme_allowed_question_intents": catalog[
            "topic_theme_allowed_question_intents"
        ],
    }
    for key in (
        "role_perspectives",
        "industry_segments",
        "jtbd_tasks",
        "desired_outputs",
        "topic_themes",
        "question_intents",
        "scope_levels",
    ):
        compact[key] = [{k: v for k, v in row.items() if k in compact_keys} for row in catalog[key]]
    schema = build_profile_topic_schema(catalog, request["count"])
    system = (
        PROFILE_TOPIC_RULES
        + "\nFocused catalog for this audience triple:\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        + "\nResponse schema:\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    if previous_response is not None:
        messages.extend(
            [
                {"role": "assistant", "content": previous_response[:40000]},
                {
                    "role": "user",
                    "content": "Fix the following errors and return the complete set of questions: "
                    + json.dumps(errors, ensure_ascii=False),
                },
            ]
        )
    return messages


def _profile_semantic_errors(
    payload: Any, audience: dict[str, str], tag_bundle: dict[str, Any]
) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("briefs"), list):
        return []
    errors, titles = [], set()
    for index, brief in enumerate(payload["briefs"]):
        if not isinstance(brief, dict):
            continue
        if brief.get("audience") != audience:
            errors.append(f"$.briefs[{index}].audience must exactly match the input triple")
        title = brief.get("title")
        normalized = " ".join(title.split()).casefold() if isinstance(title, str) else ""
        if not normalized.endswith(("?", "？")):
            errors.append(f"$.briefs[{index}].title must be a question ending in ? or ？")
        if normalized in titles:
            errors.append(f"$.briefs[{index}].title duplicates another question")
        titles.add(normalized)
        if brief.get("tags") != tag_bundle:
            errors.append(f"$.briefs[{index}].tags must exactly match the input tag_bundle")
    return errors


def validate_profile_briefs(
    payload: Any,
    catalog: dict[str, Any],
    count: int,
    audience: dict[str, str],
    tag_bundle: dict[str, Any],
) -> list[str]:
    errors = _shape_errors(payload, build_profile_topic_schema(catalog, count))
    if errors:
        return errors
    plain_payload = json.loads(json.dumps(payload))
    for brief in plain_payload["briefs"]:
        for field in ("topic_theme", "question_intent", "scope_level"):
            brief["tags"].pop(field)
    errors.extend(validate_briefs(plain_payload, catalog, count))
    errors.extend(_profile_semantic_errors(payload, audience, tag_bundle))
    return errors


def build_profile_topic_schema(
    catalog: dict[str, Any] | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """Return the Node 1 response schema with all seven maintained tag facets."""
    catalog = catalog if catalog is not None else load_brief_catalog()
    schema = build_brief_schema(catalog, count)
    schema["title"] = "Fixed-profile Node 1 topic response"
    schema["description"] = (
        "Stage 1 for one fixed audience and one fixed seven-facet tag bundle. Every brief "
        "must preserve both inputs and its title must be a displayable question. Cross-field "
        "compatibility rules are defined by the taxonomy catalog and runtime validator."
    )
    schema["x-schema-version"] = SCHEMA_VERSION
    schema["x-taxonomy-version"] = catalog["taxonomy_version"]
    schema["x-catalog-file"] = "content_brief_catalog.json"
    tags = schema["properties"]["briefs"]["items"]["properties"]["tags"]
    tags["properties"]["topic_theme"] = {
        "type": "string",
        "enum": [row["value"] for row in catalog["topic_themes"]],
    }
    tags["properties"]["question_intent"] = {
        "type": "string",
        "enum": [row["value"] for row in catalog["question_intents"]],
    }
    tags["properties"]["scope_level"] = {
        "type": "string",
        "enum": [row["value"] for row in catalog["scope_levels"]],
    }
    tags["required"].extend(("topic_theme", "question_intent", "scope_level"))
    return schema
