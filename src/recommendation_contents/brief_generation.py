"""Shared stage-one operation, with validation and one repair inside the operation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .brief_prompts import build_brief_messages
from .brief_schema import (
    LANGUAGES,
    MAX_BRIEFS,
    SCHEMA_VERSION,
    load_brief_catalog,
    parse_brief_response,
    validate_briefs,
)
from .llm import format_llm_error


def response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
            and block.get("type") in {"text", "output_text"}
        )
    else:
        raise TypeError("model returned no text content")
    if len(text) > 200000:
        raise ValueError("model response exceeds size limit")
    return text


def generate_briefs(request: dict[str, Any], get_model: Callable[[], Any]) -> dict[str, Any]:
    idea = request.get("idea")
    language, count = request.get("language", "zh-CN"), request.get("count", 1)
    errors = []
    if not isinstance(idea, str) or not idea.strip() or len(idea) > 8000:
        errors.append("idea must be a non-blank string of at most 8000 characters")
    if language not in LANGUAGES:
        errors.append("language must be zh-CN or en")
    if type(count) is not int or not 1 <= count <= MAX_BRIEFS:
        errors.append(f"count must be an integer between 1 and {MAX_BRIEFS}")
    normalized = {
        "idea": idea.strip() if isinstance(idea, str) else None,
        "language": language,
        "count": count,
    }
    catalog = load_brief_catalog()
    raw, attempts, briefs = "", 0, []
    if not errors:
        for attempt in range(2):
            attempts += 1
            try:
                messages = build_brief_messages(
                    normalized,
                    catalog,
                    previous_response=raw if attempt else None,
                    errors=errors,
                )
                raw = response_text(get_model().invoke(messages))
            except Exception as exc:  # noqa: BLE001 - model-provider boundary
                errors = [format_llm_error(exc)]
                break
            try:
                candidate = parse_brief_response(raw)
                errors = validate_briefs(candidate, catalog, count)
            except (ValueError, RecursionError):
                errors = ["Response must be a JSON object with unique keys."]
            if not errors:
                briefs = [{"brief_id": str(uuid4()), **brief} for brief in candidate["briefs"]]
                break
    return {
        "status": "failed" if errors else "succeeded",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": catalog["taxonomy_version"],
        "generation_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": normalized,
        "attempts": attempts,
        "briefs": briefs,
        "errors": errors,
    }
