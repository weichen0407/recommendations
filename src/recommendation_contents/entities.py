"""Enum entity helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_ENUM_ENTITIES_PATH = Path(__file__).resolve().parents[2] / "enum_entities.json"


def load_enum_entities(path: str | Path | None = None) -> dict[str, Any]:
    enum_path = Path(path) if path else DEFAULT_ENUM_ENTITIES_PATH
    return json.loads(enum_path.read_text(encoding="utf-8"))


def content_category_values(data: dict[str, Any] | None = None) -> list[str]:
    return _item_values((data or load_enum_entities())["content_categories"])


def role_values(data: dict[str, Any] | None = None) -> list[str]:
    return _item_values((data or load_enum_entities())["roles"])


def jtbd_values(data: dict[str, Any] | None = None) -> list[str]:
    return _item_values((data or load_enum_entities())["jtbd"])


def industry_values(data: dict[str, Any] | None = None) -> list[str]:
    return _item_values((data or load_enum_entities())["industries"])


def sub_industry_values(data: dict[str, Any] | None = None) -> list[str]:
    values: list[str] = []
    for industry in (data or load_enum_entities())["industries"]:
        for item in industry.get("sub_industries", []):
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                values.append(item["value"])
                values.extend(item.get("children", []))
    return values


def _item_values(items: list[Any]) -> list[str]:
    values = []
    for item in items:
        if isinstance(item, dict):
            values.append(item["value"])
        else:
            values.append(str(item))
    return values
