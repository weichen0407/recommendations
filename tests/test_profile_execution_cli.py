import csv
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

import recommendation_contents.profile_execution_cli as module
from recommendation_contents.brief_schema import load_brief_catalog
from recommendation_contents.profile_topic_generation import default_profile_tag_bundle
from recommendation_contents.research_prompt_generation import build_task_spec
from recommendation_contents.workflow_execution import write_run


def _node2_source(path):
    catalog = load_brief_catalog()
    audience = {
        "role": "rd_engineer",
        "industry": "materials",
        "jtbd": "technical_solutions",
    }
    tags = default_profile_tag_bundle(catalog, audience)
    generation_id = str(uuid4())
    brief_ids = [
        "ffffffff-ffff-4fff-8fff-fffffffffff1",
        "00000000-0000-4000-8000-000000000002",
    ]
    briefs = []
    specs = []
    for index, brief_id in enumerate(brief_ids, 1):
        brief = {
            "brief_id": brief_id,
            "title": f"How could AI support materials solution discovery case {index}?",
            "description": (
                "From a product design perspective across materials, identify practical AI "
                "application areas and produce a candidate shortlist for further research."
            ),
            "entities": [],
            "keywords": ["AI applications", "solution discovery"],
            "audience": audience,
            "tags": tags,
            "classification": {
                "rationale": "The question asks for broad application areas and a shortlist.",
                "industry_status": "broad_scope",
            },
            "assumptions": [],
        }
        research = {
            "brief_id": brief_id,
            "content_category": "scout_report",
            "research_instructions": (
                "Compare representative application areas using shared evidence criteria, "
                "then identify limitations and follow-up research needs."
            ),
        }
        briefs.append(brief)
        specs.append(build_task_spec(brief, research, "en", "html"))
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "workflow_version": module.NODE2_VERSION,
        "stage": "generate_research_prompt",
        "status": "succeeded",
        "created_at": now,
        "updated_at": now,
        "taxonomy_version": catalog["taxonomy_version"],
        "source": {"dataset_id": "node1-test"},
        "generations": [
            {
                "status": "succeeded",
                "tag_set_id": "test-tag-set",
                "source_generation_id": generation_id,
                "source_fingerprint": "node1-fingerprint",
                "input": {
                    "audience": audience,
                    "tag_bundle": tags,
                    "language": "en",
                    "count": 2,
                },
                "briefs": briefs,
                "format": "html",
                "research_prompt_generated_at": now,
                "task_specs": specs,
                "errors": [],
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def _args(source, output_json, output_csv, log_file, runs_dir, *extra):
    return [
        str(source),
        "--output-json",
        str(output_json),
        "--output-csv",
        str(output_csv),
        "--log-file",
        str(log_file),
        "--runs-dir",
        str(runs_dir),
        "--env-file",
        str(source.parent / "missing.env"),
        *extra,
    ]


def _fake_executor(calls):
    def execute(generation, specs, runtime, path, *, wait_for_completion, on_update, **kwargs):
        del runtime, kwargs
        spec = specs[0]
        calls.append((spec["brief_id"], spec["generated_prompt"], wait_for_completion))
        result = {
            "brief_id": spec["brief_id"],
            "status": "completed" if wait_for_completion else "submitted",
            "session_id": f"sess_{spec['brief_id'][-4:]}",
            "session_url": f"https://example/session/{spec['brief_id']}",
            "share_id": f"share_{spec['brief_id'][-4:]}",
            "share_url": f"https://example/share/{spec['brief_id']}",
            "share_status": "created",
            "isCompleted": wait_for_completion,
            "completion_status": "completed" if wait_for_completion else "",
            "completion_poll_count": int(wait_for_completion),
            "errors": [],
        }
        write_run(
            path,
            {
                "workflow_version": "2.0.0",
                "generation_result": generation,
                "task_specs": specs,
                "results": [result],
            },
        )
        on_update([result])
        return [result], "succeeded" if wait_for_completion else "pending"

    return execute


def test_dry_run_preserves_source_order_and_writes_nothing(tmp_path, monkeypatch, capsys):
    source = tmp_path / "node2.json"
    document = _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))

    assert module.main(_args(source, output_json, output_csv, log_file, runs_dir, "--dry-run")) == 0
    summary = json.loads(capsys.readouterr().out)
    tasks, _ = module._validate_and_flatten_source(document, load_brief_catalog())

    assert summary["scheduled_tasks"] == 2
    assert summary["source_status"] == "succeeded"
    assert summary["successful_source_tag_sets"] == 1
    assert summary["failed_source_tag_sets"] == 0
    assert [task["brief_id"] for task in tasks] == [
        "ffffffff-ffff-4fff-8fff-fffffffffff1",
        "00000000-0000-4000-8000-000000000002",
    ]
    assert calls == []
    assert not output_json.exists() and not output_csv.exists() and not log_file.exists()


def test_bounded_execution_checkpoints_and_resume_without_duplicate_submission(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    base = _args(source, output_json, output_csv, log_file, runs_dir)

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 0
    first = json.loads(output_json.read_text())
    assert first["status"] == "paused"
    assert [record["source_row_no"] for record in first["executions"]] == [1]
    assert calls[0][0] == "ffffffff-ffff-4fff-8fff-fffffffffff1"
    capsys.readouterr()

    assert module.main([*base, "--resume"]) == 0
    second = json.loads(output_json.read_text())
    assert second["status"] == "succeeded"
    assert [record["source_row_no"] for record in second["executions"]] == [1, 2]
    with output_csv.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["row_no"] for row in rows] == ["1", "2"]
    assert rows[0]["input"] == rows[0]["question"]
    assert rows[0]["generated_prompt"] == calls[0][1]
    assert rows[0]["session_id"] and rows[0]["share_id"]
    capsys.readouterr()

    assert module.main([*base, "--resume"]) == 0
    assert len(calls) == 2


def test_wait_for_completion_resumes_existing_session_without_resubmitting(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    base = _args(source, output_json, output_csv, log_file, runs_dir)

    assert module.main([*base, "--resume"]) == 0
    capsys.readouterr()
    assert module.main([*base, "--resume", "--wait-for-completion"]) == 0
    completed = json.loads(output_json.read_text())

    assert len(calls) == 4
    assert [call[2] for call in calls] == [False, False, True, True]
    assert all(record["isCompleted"] for record in completed["executions"])


def test_changed_prompt_is_rejected_before_execution(tmp_path, monkeypatch, capsys):
    source = tmp_path / "node2.json"
    document = _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    base = _args(source, output_json, output_csv, log_file, runs_dir)
    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 0
    capsys.readouterr()

    generation = document["generations"][0]
    spec = generation["task_specs"][0]
    spec["research_instructions"] += " Include a new criterion."
    generation["task_specs"][0] = build_task_spec(
        spec["brief"], spec, generation["input"]["language"], generation["format"]
    )
    source.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        module.main([*base, "--resume"])
    assert error.value.code == 2
    assert len(calls) == 1


def test_outer_checkpoint_lock_rejects_second_runner(tmp_path):
    output = tmp_path / "node3.json"
    outer_lock = module._batch_lock(output)
    expected_error = pytest.raises(module.BatchFileError, match="already executing")
    inner_lock = module._batch_lock(output)
    with outer_lock, expected_error, inner_lock:
        pass


def test_execution_error_is_visible_and_retryable(tmp_path, monkeypatch, capsys):
    source = tmp_path / "node2.json"
    _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    attempts = []

    def fail_execution(*args, **kwargs):
        attempts.append((args, kwargs))
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module, "execute_tasks", fail_execution)
    base = _args(source, output_json, output_csv, log_file, runs_dir)

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 1
    first = json.loads(output_json.read_text())
    assert first["status"] == "failed"
    assert first["progress"]["execution_error_tasks"] == 1
    assert first["executions"][0]["execution_status"] == "execution_error"
    capsys.readouterr()

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 1
    assert len(attempts) == 2
