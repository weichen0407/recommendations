import json
from pathlib import Path

from recommendation_contents.schemas import (
    article_metadata_extraction_schema,
    prompt_generation_output_schema,
)


def test_enum_entities_json_is_valid_and_deduplicated():
    data = json.loads(Path("enum_entities.json").read_text(encoding="utf-8"))

    for key in ["content_categories", "roles", "jtbd"]:
        values = [item["value"] for item in data[key]]
        assert len(values) == len(set(values))

    role_values = {item["value"] for item in data["roles"]}
    jtbd_values = {item["value"] for item in data["jtbd"]}

    assert set(data["role_jtbd_map"]) == role_values
    for values in data["role_jtbd_map"].values():
        assert set(values).issubset(jtbd_values)

    assert data["industries"]


def test_prompt_generation_schema_uses_enum_values():
    schema = prompt_generation_output_schema()

    assert "categories" in schema["required"]
    assert "prompt" in schema["required"]
    assert "scout_report" in schema["properties"]["categories"]["items"]["enum"]
    assert "innovation_product_strategy" in schema["properties"]["role"]["enum"]
    assert "ev_and_battery_systems" in schema["properties"]["sub_industry"]["items"]["enum"]


def test_article_metadata_extraction_schema_uses_enum_values_without_prompt():
    schema = article_metadata_extraction_schema()

    assert "categories" in schema["required"]
    assert "prompt" not in schema["required"]
    assert "prompt" not in schema["properties"]
    assert "scout_report" in schema["properties"]["categories"]["items"]["enum"]
    assert "innovation_product_strategy" in schema["properties"]["role"]["enum"]
    assert "ev_and_battery_systems" in schema["properties"]["sub_industry"]["items"]["enum"]
