import csv
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

import recommendation_contents.profile_execution_cli as module
from recommendation_contents.brief_schema import load_brief_catalog
from recommendation_contents.profile_topic_generation import default_profile_tag_bundle
from recommendation_contents.research_prompt_generation import HTML_INSTRUCTION, build_task_spec


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
                "research_prompt_generated_at": now,
                "task_specs": specs,
                "errors": [],
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def _args(source, output_json, output_csv, log_file, runs_dir, *extra):
    del runs_dir
    return [
        str(source),
        "--state-db",
        str(output_json),
        "--output-json",
        str(output_json.with_name("node3-manifest.json")),
        "--output-csv",
        str(output_csv),
        "--log-file",
        str(log_file),
        "--format",
        "html",
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
        path.write_run(
            {
                "workflow_version": "2.0.0",
                "generation_result": generation,
                "task_specs": specs,
                "results": [result],
            }
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
    tasks, _ = module._validate_and_flatten_source(document, load_brief_catalog(), "html")

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


def test_prepare_only_creates_complete_json_and_csv_then_bootstraps_execution(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    output_json = tmp_path / "node3-manifest.json"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)
    manifest_index = args.index("--output-json") + 1
    args[manifest_index] = str(output_json)

    assert module.main([*args, "--prepare-only", "--overwrite"]) == 0
    manifest = json.loads(output_json.read_text())
    with output_csv.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(manifest["executions"]) == len(rows) == 2
    assert {record["execution_status"] for record in manifest["executions"]} == {
        "not_started"
    }
    assert all(record["brief_id"] for record in manifest["executions"])
    assert all(
        record["question_id"] == record["brief_id"]
        for record in manifest["executions"]
    )
    assert all(row["question_id"] == row["brief_id"] for row in rows)
    assert not state_db.exists() and not log_file.exists()
    capsys.readouterr()

    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    assert module.main([*args, "--resume", "--max-tasks", "1"]) == 0
    assert state_db.exists() and log_file.exists()
    assert len(calls) == 1


def test_reviewed_manifest_prompt_override_is_the_prompt_executed(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    output_json = tmp_path / "manifest.json"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)
    args[args.index("--output-json") + 1] = str(output_json)
    assert module.main([*args, "--prepare-only", "--overwrite"]) == 0
    capsys.readouterr()

    document = json.loads(output_json.read_text())
    original_fingerprint = document["executions"][0]["source_fingerprint"]
    reviewed_prompt = "Reviewed compact HTML execution prompt."
    document["executions"][0]["generated_prompt"] = reviewed_prompt
    output_json.write_text(json.dumps(document), encoding="utf-8")

    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    assert module.main([*args, "--resume", "--max-tasks", "1"]) == 0

    checkpoint = module._read_checkpoint(state_db)
    assert calls[0][1] == reviewed_prompt
    assert checkpoint["executions"][0]["generated_prompt"] == reviewed_prompt
    assert checkpoint["executions"][0]["source_fingerprint"] != original_fingerprint


def test_auth_wait_import_retries_current_task_after_authorization_changes(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)
    waits = []
    calls = []

    monkeypatch.setattr(module, "_authorization_ready", lambda runtime: False)
    monkeypatch.setattr(module, "_auth_snapshot", lambda runtime: {})

    def wait_for_auth(runtime, **kwargs):
        del runtime
        waits.append(kwargs["attempt"])
        return True

    def execute(generation, specs, runtime, path, *, on_update, **kwargs):
        del generation, runtime, kwargs
        calls.append(specs[0]["brief_id"])
        status = "needs_auth" if len(calls) == 1 else "submitted"
        result = {
            "brief_id": specs[0]["brief_id"],
            "status": status,
            "session_id": "" if status == "needs_auth" else "sess_retry",
            "session_url": "" if status == "needs_auth" else "https://example/session/retry",
            "share_id": "" if status == "needs_auth" else "share_retry",
            "share_url": "" if status == "needs_auth" else "https://example/share/retry",
            "share_status": "pending" if status == "needs_auth" else "created",
            "isCompleted": False,
            "completion_status": "",
            "completion_poll_count": 0,
            "errors": ["401"] if status == "needs_auth" else [],
        }
        path.write_run(
            {
                "workflow_version": "2.0.0",
                "generation_result": {},
                "task_specs": specs,
                "results": [result],
            }
        )
        on_update([result])
        return [result], status

    monkeypatch.setattr(module, "_wait_for_auth_update", wait_for_auth)
    monkeypatch.setattr(module, "execute_tasks", execute)

    assert module.main(
        [
            *args,
            "--resume",
            "--max-tasks",
            "1",
            "--wait-on-401",
            "60",
            "--retry-on-auth-change",
            "--retry-attempts",
            "2",
            "--import-clipboard-on-401",
        ]
    ) == 0
    assert waits == [0, 1]
    assert len(calls) == 2
    assert module._read_checkpoint(state_db)["executions"][0]["session_id"] == "sess_retry"
    capsys.readouterr()


def test_retry_failed_resets_only_the_scheduled_rejected_task(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)
    failed_calls = []

    def fail(generation, specs, runtime, path, *, on_update, **kwargs):
        del generation, runtime, kwargs
        failed_calls.append(specs[0]["brief_id"])
        result = {
            "brief_id": specs[0]["brief_id"],
            "status": "failed",
            "session_id": "",
            "session_url": "",
            "share_id": "",
            "share_url": "",
            "share_status": "pending",
            "isCompleted": False,
            "completion_status": "",
            "completion_poll_count": 0,
            "errors": ["Eureka rejected the task submission."],
        }
        path.write_run(
            {
                "workflow_version": "2.0.0",
                "generation_result": {},
                "task_specs": specs,
                "results": [result],
            }
        )
        on_update([result])
        return [result], "failed"

    monkeypatch.setattr(module, "execute_tasks", fail)
    assert module.main([*args, "--resume", "--max-tasks", "1"]) == 1
    capsys.readouterr()

    successful_calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(successful_calls))
    assert module.main([*args, "--resume", "--retry-failed", "--max-tasks", "1"]) == 0

    checkpoint = module._read_checkpoint(state_db)
    assert failed_calls == ["ffffffff-ffff-4fff-8fff-fffffffffff1"]
    assert successful_calls[0][0] == failed_calls[0]
    assert checkpoint["executions"][0]["session_id"]
    assert checkpoint["executions"][1]["execution_status"] == "not_started"
    capsys.readouterr()


def test_retry_uncertain_links_resubmits_unknown_task_without_ids(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)
    calls = []

    def uncertain(generation, specs, runtime, path, *, on_update, **kwargs):
        del generation, runtime, kwargs
        spec = specs[0]
        calls.append(spec["brief_id"])
        result = {
            "brief_id": spec["brief_id"],
            "status": "submission_unknown",
            "session_id": "",
            "session_url": "",
            "share_id": "",
            "share_url": "",
            "share_status": "pending",
            "isCompleted": False,
            "completion_status": "",
            "completion_poll_count": 0,
            "errors": ["Submission outcome is uncertain; do not auto-resubmit."],
        }
        path.write_run(
            {
                "workflow_version": "2.0.0",
                "generation_result": {},
                "task_specs": specs,
                "results": [result],
            }
        )
        on_update([result])
        return [result], "failed"

    monkeypatch.setattr(module, "execute_tasks", uncertain)
    assert module.main([*args, "--resume", "--max-tasks", "1"]) == 1
    capsys.readouterr()

    successful_calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(successful_calls))
    assert module.main(
        [*args, "--resume", "--retry-uncertain-links", "--max-tasks", "1"]
    ) == 0
    checkpoint = module._read_checkpoint(state_db)
    assert calls == ["ffffffff-ffff-4fff-8fff-fffffffffff1"]
    assert successful_calls[0][0] == calls[0]
    assert checkpoint["executions"][0]["session_id"]
    capsys.readouterr()


def test_retry_uncertain_links_reuses_session_and_retries_share_only(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    _node2_source(source)
    state_db, output_csv = tmp_path / "state.sqlite", tmp_path / "results.csv"
    log_file, unused_runs_dir = tmp_path / "run.log", tmp_path / "unused-runs"
    args = _args(source, state_db, output_csv, log_file, unused_runs_dir)

    def uncertain_share(generation, specs, runtime, path, *, on_update, **kwargs):
        del generation, runtime, kwargs
        spec = specs[0]
        result = {
            "brief_id": spec["brief_id"],
            "status": "submitted",
            "session_id": "sess_existing",
            "session_url": "https://example/session/existing",
            "share_id": "",
            "share_url": "",
            "share_status": "submission_unknown",
            "share_error": "Share creation returned no confirmed share ID.",
            "isCompleted": False,
            "completion_status": "",
            "completion_poll_count": 0,
            "errors": ["Share creation returned no confirmed share ID."],
        }
        path.write_run(
            {
                "workflow_version": "2.0.0",
                "generation_result": {},
                "task_specs": specs,
                "results": [result],
            }
        )
        on_update([result])
        return [result], "pending"

    monkeypatch.setattr(module, "execute_tasks", uncertain_share)
    assert module.main([*args, "--resume", "--max-tasks", "1"]) == 1
    capsys.readouterr()

    seen = []

    def repair_share(generation, specs, runtime, path, *, on_update, **kwargs):
        del generation, runtime, kwargs
        saved = path.read_run()
        prior = saved["results"][0]
        seen.append((prior["session_id"], prior["share_status"], prior["status"]))
        result = {
            **prior,
            "status": "submitted",
            "share_id": "share_repaired",
            "share_url": "https://example/share/repaired",
            "share_status": "created",
            "share_error": "",
            "errors": [],
        }
        saved["results"] = [result]
        path.write_run(saved)
        on_update([result])
        return [result], "pending"

    monkeypatch.setattr(module, "execute_tasks", repair_share)
    assert module.main(
        [*args, "--resume", "--retry-uncertain-links", "--max-tasks", "1"]
    ) == 0
    checkpoint = module._read_checkpoint(state_db)
    assert seen == [("sess_existing", "pending", "submitted")]
    assert checkpoint["executions"][0]["session_id"] == "sess_existing"
    assert checkpoint["executions"][0]["share_id"] == "share_repaired"
    capsys.readouterr()

def test_bounded_execution_checkpoints_and_resume_without_duplicate_submission(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "node2.json"
    source_document = _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    base = _args(source, output_json, output_csv, log_file, runs_dir)

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 0
    first = module._read_checkpoint(output_json)
    assert first["status"] == "paused"
    assert [record["source_row_no"] for record in first["executions"]] == [1, 2]
    assert calls[0][0] == "ffffffff-ffff-4fff-8fff-fffffffffff1"
    assert calls[0][1].startswith(f"{HTML_INSTRUCTION}\n\n")
    assert (
        HTML_INSTRUCTION
        not in source_document["generations"][0]["task_specs"][0]["generated_prompt"]
    )
    with output_csv.open(encoding="utf-8-sig", newline="") as file:
        first_rows = list(csv.DictReader(file))
    assert len(first_rows) == 2
    assert [row["execution_status"] for row in first_rows] == ["submitted", "not_started"]
    capsys.readouterr()

    assert module.main([*base, "--resume"]) == 0
    second = module._read_checkpoint(output_json)
    assert second["status"] == "succeeded"
    assert [record["source_row_no"] for record in second["executions"]] == [1, 2]
    with output_csv.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["row_no"] for row in rows] == ["1", "2"]
    assert rows[0]["input"] == rows[0]["question"]
    assert rows[0]["generated_prompt"] == calls[0][1]
    assert rows[0]["session_id"] and rows[0]["share_id"]
    assert not runs_dir.exists()
    assert not output_json.with_name(output_json.name + ".lock").exists()
    with module._state_connection(output_json) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 2
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
    completed = module._read_checkpoint(output_json)

    assert len(calls) == 4
    assert [call[2] for call in calls] == [False, False, True, True]
    assert all(record["isCompleted"] for record in completed["executions"])


def test_resume_rejects_a_different_execution_format(tmp_path, monkeypatch, capsys):
    source = tmp_path / "node2.json"
    _node2_source(source)
    output_json, output_csv = tmp_path / "node3.json", tmp_path / "node3.csv"
    log_file, runs_dir = tmp_path / "node3.log", tmp_path / "runs"
    calls = []
    monkeypatch.setattr(module, "execute_tasks", _fake_executor(calls))
    base = _args(source, output_json, output_csv, log_file, runs_dir)

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 0
    capsys.readouterr()
    report_args = ["report" if value == "html" else value for value in base]

    with pytest.raises(SystemExit) as error:
        module.main([*report_args, "--resume"])
    assert error.value.code == 2
    assert len(calls) == 1


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
        spec["brief"], spec, generation["input"]["language"]
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
    first = module._read_checkpoint(output_json)
    assert first["status"] == "failed"
    assert first["progress"]["execution_error_tasks"] == 1
    assert first["executions"][0]["execution_status"] == "execution_error"
    capsys.readouterr()

    assert module.main([*base, "--max-tasks", "1", "--resume"]) == 1
    assert len(attempts) == 2
