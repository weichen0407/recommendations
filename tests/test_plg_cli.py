import csv
import json
from pathlib import Path

from recommendation_contents.plg_cli import (
    default_plg_output_path,
    infer_format_from_path,
    plg_item_from_row,
    update_records_csv_format,
    write_plg_json,
)


def test_plg_item_from_row_extracts_ids_and_parses_lists():
    item = plg_item_from_row(
        {
            "input": "Input",
            "generated_prompt": "Prompt",
            "session_url": "https://eureka.patsnap.com/ai-search/sess_abc123",
            "share_url": (
                "https://eureka-service.patsnap.com/eureka/share/result?"
                "id=share123&from=invite"
            ),
            "categories": "[\"case\"]",
            "keywords": "[\"wearable\", \"health\"]",
            "jtbd": "[\"innovation_opportunities\"]",
            "sub_industry": "[\"wearable_and_digital_health_devices\"]",
            "isCompleted": "true",
        },
        "html",
    )

    assert item["session_id"] == "sess_abc123"
    assert item["share_id"] == "share123"
    assert item["format"] == "html"
    assert item["categories"] == ["case"]
    assert item["keywords"] == ["wearable", "health"]
    assert item["jtbd"] == ["innovation_opportunities"]
    assert item["sub_industry"] == ["wearable_and_digital_health_devices"]
    assert item["isCompleted"] == "true"


def test_update_records_csv_format_inserts_format_after_share_url(tmp_path):
    records_path = tmp_path / "html" / "recommend_content_091017_html_records.csv"
    records_path.parent.mkdir()
    records_path.write_text(
        "input,generated_prompt,session_url,share_url,isCompleted\n"
        "Input,Prompt,https://eureka.test/sess_1,https://share.test/?id=share_1,true\n",
        encoding="utf-8",
    )

    assert update_records_csv_format(records_path, "html") == 1

    with records_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == [
        "input",
        "generated_prompt",
        "session_url",
        "share_url",
        "format",
        "isCompleted",
    ]
    assert rows[0]["format"] == "html"


def test_format_inference_and_default_output_path():
    records_path = Path("outputs/0910/091017/html/recommend_content_091017_html_records.csv")

    assert infer_format_from_path(records_path) == "html"
    assert str(default_plg_output_path(records_path)).endswith(
        "outputs/0910/091017/html/plg-rd-case-default-us.json"
    )


def test_write_plg_json_keeps_list_values_unescaped(tmp_path):
    output_path = tmp_path / "plg-rd-case-default-us.json"
    write_plg_json([{"keywords": ["wearable", "health"]}], output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == [{"keywords": ["wearable", "health"]}]
    assert '"keywords": [' in output_path.read_text(encoding="utf-8")
