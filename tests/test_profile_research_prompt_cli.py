import csv
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

import recommendation_contents.profile_research_prompt_cli as module
from recommendation_contents.brief_schema import SCHEMA_VERSION, load_brief_catalog
from recommendation_contents.profile_topic_generation import (
    default_profile_tag_bundle,
    profile_tag_set_id,
)
from recommendation_contents.research_prompt_generation import GenerationError, build_task_spec


def _generation(industry: str):
    catalog = load_brief_catalog()
    audience = {
        "role": "rd_engineer",
        "industry": industry,
        "jtbd": "technical_solutions",
    }
    tags = default_profile_tag_bundle(catalog, audience)
    brief = {
        "brief_id": str(uuid4()),
        "title": f"How could AI support solution discovery across the {industry} industry?",
        "description": (
            f"From a product design perspective, identify practical AI application areas across "
            f"the {industry} industry and produce a candidate shortlist for further research."
        ),
        "entities": [],
        "keywords": ["AI applications", "solution discovery"],
        "audience": audience,
        "tags": tags,
        "classification": {
            "rationale": "The question keeps an industry-wide scope and asks for application areas.",
            "industry_status": "broad_scope",
        },
        "assumptions": [],
    }
    return {
        "status": "succeeded",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": catalog["taxonomy_version"],
        "tag_set_id": profile_tag_set_id(audience, tags),
        "generation_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "audience": audience,
            "tag_bundle": tags,
            "language": "en",
            "count": 1,
        },
        "attempts": 1,
        "briefs": [brief],
        "errors": [],
    }


def _source(path, industries=("electronics_manufacturing", "materials")):
    catalog = load_brief_catalog()
    document = {
        "workflow_version": module.NODE1_VERSION,
        "stage": "generate_topic",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": catalog["taxonomy_version"],
        "scope": {},
        "progress": {},
        "generations": [_generation(industry) for industry in industries],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def _successful_generator(calls):
    def generate(generation, output_format, get_model):
        calls.append(generation["tag_set_id"])
        specs = []
        for brief in generation["briefs"]:
            research_prompt = {
                "brief_id": brief["brief_id"],
                "content_category": "scout_report",
                "research_instructions": (
                    "Compare representative application areas using shared evidence criteria, "
                    "then identify limitations and follow-up research needs."
                ),
            }
            specs.append(
                build_task_spec(
                    brief,
                    research_prompt,
                    generation["input"]["language"],
                    output_format,
                )
            )
        return specs, 1

    return generate


def _args(source, output_json, output_csv, *extra):
    return [
        str(source),
        "--output-json",
        str(output_json),
        "--output-csv",
        str(output_csv),
        "--workers",
        "1",
        *extra,
    ]


def test_bounded_run_checkpoints_and_resume_complete_the_remaining_batches(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path)
    original_source = source_path.read_bytes()
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))

    assert (
        module.main(
            _args(source_path, output_json, output_csv, "--overwrite", "--max-batches", "1")
        )
        == 0
    )
    first_capture = capsys.readouterr()
    first_summary = json.loads(first_capture.out)
    first = json.loads(output_json.read_text())
    assert first_summary["status"] == first["status"] == "paused"
    assert first["workflow_version"] == "profile-topic-node2/1.0.0"
    assert first["stage"] == "generate_research_prompt"
    assert first["progress"] == {
        "eligible_tag_sets": 2,
        "succeeded_tag_sets": 1,
        "failed_tag_sets": 0,
        "pending_tag_sets": 1,
        "generated_rows": 1,
    }
    assert first_summary["eureka_calls"] == 0
    assert source_path.read_bytes() == original_source
    with output_csv.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["research_instructions"]
    assert rows[0]["execution_status"] == "not_started"
    assert "rows=1" in first_capture.err
    log_path = output_json.with_suffix(".log")
    first_log = log_path.read_text()
    assert "generate_research_prompt: selected=2" in first_log
    assert "rows=1" in first_log
    assert "run_finished:" in first_log

    assert (
        module.main(_args(source_path, output_json, output_csv, "--resume", "--max-batches", "1"))
        == 0
    )
    second_summary = json.loads(capsys.readouterr().out)
    second = json.loads(output_json.read_text())
    assert second_summary["status"] == second["status"] == "succeeded"
    assert second["progress"]["succeeded_tag_sets"] == 2
    assert second["progress"]["generated_rows"] == 2
    assert len(calls) == 2
    resumed_log = log_path.read_text()
    assert resumed_log.startswith(first_log)
    assert resumed_log.count("generate_research_prompt:") == 2

    assert module.main(_args(source_path, output_json, output_csv, "--resume")) == 0
    final_summary = json.loads(capsys.readouterr().out)
    assert final_summary["scheduled_batches"] == 0
    assert final_summary["already_succeeded"] == 2
    assert len(calls) == 2


def test_resume_rebuilds_prompt_from_maintained_structured_fields_without_model_call(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    capsys.readouterr()

    document = json.loads(output_json.read_text())
    spec = document["generations"][0]["task_specs"][0]
    old_prompt = spec["generated_prompt"]
    spec["research_instructions"] = (
        "Use the maintained review criteria, cite identifiable evidence, and list open questions."
    )
    output_json.write_text(json.dumps(document), encoding="utf-8")

    assert module.main(_args(source_path, output_json, output_csv, "--resume")) == 0
    summary = json.loads(capsys.readouterr().out)
    maintained = json.loads(output_json.read_text())["generations"][0]["task_specs"][0]
    assert summary["scheduled_batches"] == 0
    assert len(calls) == 1
    assert maintained["generated_prompt"] != old_prompt
    assert "Use the maintained review criteria" in maintained["generated_prompt"]


def test_source_edit_makes_a_completed_batch_stale_and_regenerates_it(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    source = _source(source_path, ("electronics_manufacturing",))
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    capsys.readouterr()

    source["generations"][0]["briefs"][0]["description"] += " Include adoption constraints."
    source["updated_at"] = datetime.now(timezone.utc).isoformat()
    source_path.write_text(json.dumps(source), encoding="utf-8")
    assert module.main(_args(source_path, output_json, output_csv, "--resume")) == 0
    summary = json.loads(capsys.readouterr().out)
    record = json.loads(output_json.read_text())["generations"][0]
    assert summary["scheduled_batches"] == 1
    assert len(calls) == 2
    assert record["briefs"][0]["description"].endswith("Include adoption constraints.")


def test_bounded_regeneration_becomes_persistent_pending_work(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path)
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    capsys.readouterr()

    assert (
        module.main(
            _args(
                source_path,
                output_json,
                output_csv,
                "--resume",
                "--regenerate-selected",
                "--max-batches",
                "1",
            )
        )
        == 0
    )
    partial = json.loads(output_json.read_text())
    assert partial["status"] == "paused"
    assert partial["progress"]["succeeded_tag_sets"] == 1
    assert partial["progress"]["pending_tag_sets"] == 1
    assert len(calls) == 3
    capsys.readouterr()

    assert (
        module.main(
            _args(source_path, output_json, output_csv, "--resume", "--max-batches", "1")
        )
        == 0
    )
    completed = json.loads(output_json.read_text())
    assert completed["status"] == "succeeded"
    assert completed["progress"]["succeeded_tag_sets"] == 2
    assert len(calls) == 4


def test_resume_prunes_stale_records_even_when_filter_excludes_them(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    source = _source(source_path)
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    capsys.readouterr()

    stale = source["generations"][0]
    stale["briefs"][0]["description"] += " Include adoption constraints."
    source["updated_at"] = datetime.now(timezone.utc).isoformat()
    source_path.write_text(json.dumps(source), encoding="utf-8")
    assert (
        module.main(
            _args(
                source_path,
                output_json,
                output_csv,
                "--resume",
                "--industry",
                "materials",
            )
        )
        == 0
    )
    checkpoint = json.loads(output_json.read_text())
    assert checkpoint["status"] == "paused"
    assert checkpoint["progress"]["pending_tag_sets"] == 1
    assert {row["tag_set_id"] for row in checkpoint["generations"]} == {
        source["generations"][1]["tag_set_id"]
    }
    assert len(calls) == 2


def test_failed_batch_is_checkpointed_and_retried_on_resume(tmp_path, monkeypatch, capsys):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))

    def fail(*_args):
        raise GenerationError("generate_research_prompt", ["test failure"])

    monkeypatch.setattr(module, "generate_research_prompt_specs", fail)
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 1
    failed = json.loads(output_json.read_text())
    assert failed["status"] == "failed"
    assert failed["progress"]["failed_tag_sets"] == 1
    assert failed["generations"][0]["research_prompt_attempts"] is None
    capsys.readouterr()

    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    assert module.main(_args(source_path, output_json, output_csv, "--resume")) == 0
    resumed = json.loads(output_json.read_text())
    assert resumed["status"] == "succeeded"
    assert resumed["progress"]["failed_tag_sets"] == 0
    assert calls


def test_dry_run_does_not_write_or_call_model(tmp_path, monkeypatch, capsys):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))

    assert module.main(_args(source_path, output_json, output_csv, "--dry-run")) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "dry_run"
    assert summary["scheduled_batches"] == 1
    assert not output_json.exists() and not output_csv.exists()
    assert not output_json.with_suffix(".log").exists()
    assert calls == []


def test_node2_does_not_parse_unrelated_eureka_settings(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    calls = []
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator(calls))
    monkeypatch.setenv("EUREKA_COMPLETION_TIMEOUT_SECONDS", "not-a-number")

    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    assert json.loads(capsys.readouterr().out)["eureka_calls"] == 0
    assert len(calls) == 1


def test_ctrl_c_drains_in_flight_result_to_atomic_checkpoint(tmp_path, monkeypatch, capsys):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator([]))
    real_as_completed = module.as_completed
    iterations = 0

    def interrupt_once(futures):
        nonlocal iterations
        iterations += 1
        if iterations == 1:
            raise KeyboardInterrupt
        yield from real_as_completed(futures)

    monkeypatch.setattr(module, "as_completed", interrupt_once)
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 130
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    checkpoint = json.loads(output_json.read_text())
    assert summary["status"] == checkpoint["status"] == "paused"
    assert checkpoint["progress"]["succeeded_tag_sets"] == 1
    assert "Waiting for" in captured.err


@pytest.mark.parametrize("same_output", ["json", "csv"])
def test_node2_can_never_overwrite_node1_input(tmp_path, same_output):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    if same_output == "json":
        output_json = source_path
    else:
        output_csv = source_path
    with pytest.raises(SystemExit) as error:
        module.main(_args(source_path, output_json, output_csv, "--dry-run"))
    assert error.value.code == 2


def test_json_and_csv_outputs_must_be_distinct(tmp_path):
    source_path = tmp_path / "node1.json"
    shared_output = tmp_path / "node2.json"
    _source(source_path, ("electronics_manufacturing",))
    with pytest.raises(SystemExit) as error:
        module.main(_args(source_path, shared_output, shared_output, "--dry-run"))
    assert error.value.code == 2


def test_malformed_resume_scope_returns_cli_validation_error(
    tmp_path, monkeypatch, capsys
):
    source_path = tmp_path / "node1.json"
    output_json, output_csv = tmp_path / "node2.json", tmp_path / "node2.csv"
    _source(source_path, ("electronics_manufacturing",))
    monkeypatch.setattr(module, "generate_research_prompt_specs", _successful_generator([]))
    assert module.main(_args(source_path, output_json, output_csv, "--overwrite")) == 0
    capsys.readouterr()
    checkpoint = json.loads(output_json.read_text())
    checkpoint["scope"] = []
    output_json.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        module.main(_args(source_path, output_json, output_csv, "--resume"))
    assert error.value.code == 2
