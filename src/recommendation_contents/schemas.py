"""JSON schemas used by the workflow."""

from __future__ import annotations

from typing import Any

from .entities import (
    content_category_values,
    industry_values,
    jtbd_values,
    role_values,
    sub_industry_values,
)


def prompt_generation_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "categories",
            "keywords",
            "description",
            "role",
            "industry",
            "jtbd",
            "date",
            "sub_industry",
            "prompt",
        ],
        "properties": {
            **_record_metadata_properties(),
            "prompt": {
                "type": "string",
                "description": "Complete prompt that Eureka should execute.",
            },
        },
    }


def article_metadata_extraction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "categories",
            "keywords",
            "description",
            "role",
            "industry",
            "jtbd",
            "date",
            "sub_industry",
        ],
        "properties": _record_metadata_properties(),
    }


def _record_metadata_properties() -> dict[str, Any]:
    return {
        "title": {
            "type": "string",
            "description": "Concise, searchable article or report title.",
        },
        "categories": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
                "enum": content_category_values(),
            },
        },
        "keywords": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
            },
        },
        "description": {
            "type": "string",
            "description": "One to two sentence summary.",
        },
        "role": {
            "type": "string",
            "enum": role_values(),
        },
        "industry": {
            "type": "string",
            "enum": industry_values(),
        },
        "jtbd": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
                "enum": jtbd_values(),
            },
        },
        "date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format.",
        },
        "sub_industry": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": sub_industry_values(),
            },
        },
    }
