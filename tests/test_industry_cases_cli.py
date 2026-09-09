import json
import sys

import pytest

from recommendation_contents import industry_cases_cli
from recommendation_contents.industry_cases_cli import (
    build_selection_payload,
    mark_selected,
    read_usage_rows,
    select_unused_cases_by_industry,
    update_usage_after_run,
    write_selection_json,
    write_usage_rows,
)


def test_select_unused_cases_by_industry_caps_each_industry_and_skips_used():
    records = [
        {"title": "auto used", "industry": "automotive"},
        {"title": "auto one", "industry": "automotive"},
        {"title": "auto two", "industry": "automotive"},
        {"title": "auto three", "industry": "automotive"},
        {"title": "energy one", "industry": "energy"},
        {"title": "energy two", "industry": "energy"},
    ]
    usage_rows = {
        0: {
            "case_index": "0",
            "title": "auto used",
            "industry": "automotive",
            "status": "used",
        }
    }

    selected = select_unused_cases_by_industry(records, usage_rows, per_industry=2)

    assert [index for index, _item in selected["automotive"]] == [1, 2]
    assert [index for index, _item in selected["energy"]] == [4, 5]


def test_select_unused_cases_by_industry_preserves_embedded_case_index():
    records = [
        {"case_index": 67, "title": "auto used", "industry": "automotive"},
        {"case_index": 120, "title": "auto one", "industry": "automotive"},
        {"case_index": 140, "title": "energy one", "industry": "energy"},
    ]
    usage_rows = {
        67: {
            "case_index": "67",
            "title": "auto used",
            "industry": "automotive",
            "status": "used",
        }
    }

    selected = select_unused_cases_by_industry(records, usage_rows, per_industry=30)

    assert [index for index, _item in selected["automotive"]] == [120]
    assert [index for index, _item in selected["energy"]] == [140]


def test_select_unused_cases_by_industry_can_filter_industries():
    records = [
        {"title": "auto one", "industry": "automotive"},
        {"title": "energy one", "industry": "energy"},
    ]

    selected = select_unused_cases_by_industry(records, {}, per_industry=30, allowed_industries={"energy"})

    assert list(selected) == ["energy"]
    assert selected["energy"][0][0] == 1


def test_usage_table_marks_selected_and_used(tmp_path):
    usage_path = tmp_path / "case_usage.csv"
    usage_rows = {}
    item = {"title": "auto one", "industry": "automotive"}

    mark_selected(usage_rows, 3, item)
    write_usage_rows(usage_rows, str(usage_path))
    selected_rows = read_usage_rows(str(usage_path))

    assert selected_rows[3]["status"] == "selected"
    assert selected_rows[3]["title"] == "auto one"
    assert selected_rows[3]["selected_at"]

    update_usage_after_run(
        selected_rows,
        3,
        item,
        {
            "curl_success": True,
            "session_url": "https://eureka.patsnap.com/ai-search/sess",
            "share_url": "https://eureka.patsnap.com/share/?id=share",
            "errors": [],
        },
    )
    write_usage_rows(selected_rows, str(usage_path))
    used_rows = read_usage_rows(str(usage_path))

    assert used_rows[3]["status"] == "used"
    assert used_rows[3]["used_at"]
    assert used_rows[3]["session_url"].endswith("/sess")
    assert used_rows[3]["share_url"].endswith("share")


def test_industry_main_stops_before_next_case_when_url_is_missing(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.json"
    env_path = tmp_path / ".env"
    usage_path = tmp_path / "usage.csv"
    records_path = tmp_path / "records.csv"
    results_path = tmp_path / "results.json"
    cases_path.write_text(
        json.dumps(
            [
                {"title": "first", "industry": "materials", "output": "prompt first"},
                {"title": "second", "industry": "materials", "output": "prompt second"},
            ]
        ),
        encoding="utf-8",
    )
    env_path.write_text("", encoding="utf-8")
    calls = []

    def fake_run_case_item(case_index, item, runtime, **_kwargs):
        calls.append(case_index)
        return {
            "case_index": case_index,
            "input": item["title"],
            "title": item["title"],
            "generated_prompt": item["output"],
            "session_url": "",
            "share_url": "",
            "curl_success": False,
            "errors": ["Eureka query returned business error: no credits"],
            "row": {
                "input": item["title"],
                "generated_prompt": item["output"],
                "session_url": "",
                "share_url": "",
            },
        }

    monkeypatch.setattr(industry_cases_cli, "run_case_item", fake_run_case_item)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-case-workflow",
            str(cases_path),
            "--env-file",
            str(env_path),
            "--per-industry",
            "2",
            "--usage-csv",
            str(usage_path),
            "--records-csv",
            str(records_path),
            "--results-json",
            str(results_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        industry_cases_cli.main()

    usage_rows = read_usage_rows(str(usage_path))
    assert calls == [0]
    assert "stop before next case" in str(exc_info.value)
    assert usage_rows[0]["status"] == "failed"
    assert not records_path.exists()
    assert len(json.loads(results_path.read_text(encoding="utf-8"))) == 1


def test_selection_payload_keeps_flat_items_and_by_industry(tmp_path):
    selected = {
        "automotive": [
            (
                3,
                {
                    "title": "auto one",
                    "industry": "automotive",
                    "categories": ["competitor_analysis"],
                    "keywords": ["battery"],
                    "description": "desc",
                    "role": "innovation_product_strategy",
                    "jtbd": ["track_technologies_and_competitors"],
                    "date": "2026-09-08",
                    "sub_industry": ["ev_and_battery_systems"],
                    "output": "prompt",
                },
            )
        ]
    }
    output_path = tmp_path / "selection.json"

    payload = build_selection_payload(
        cases_json="cases/500articles.json",
        usage_csv="cases/case_usage.csv",
        selected=selected,
        per_industry=30,
    )
    write_selection_json(payload, str(output_path))

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["total"] == 1
    assert saved["selected_by_industry"] == {"automotive": 1}
    assert saved["items"][0]["case_index"] == 3
    assert saved["items"][0]["output"] == "prompt"
    assert saved["by_industry"]["automotive"][0]["title"] == "auto one"


def test_usage_table_marks_failed_without_used_at():
    usage_rows = {}
    item = {"title": "auto one", "industry": "automotive"}

    update_usage_after_run(
        usage_rows,
        3,
        item,
        {
            "curl_success": False,
            "session_url": "",
            "share_url": "",
            "errors": ["Eureka query returned HTTP 401"],
        },
    )

    assert usage_rows[3]["status"] == "failed"
    assert usage_rows[3]["used_at"] == ""
    assert usage_rows[3]["error"] == "Eureka query returned HTTP 401"
