import json
from pathlib import Path


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
