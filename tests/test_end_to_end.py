import copy
import json
from pathlib import Path

import pytest

from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    OpenAISettings,
)
from recommendation_contents.graph import build_graph_with_dependencies
from recommendation_contents.nodes import RuntimeDependencies
from recommendation_contents.research_prompt_generation import (
    HTML_INSTRUCTION,
    REPORT_INSTRUCTION,
    GenerationError,
)
from recommendation_contents.services.eureka_curl import CurlResult, EurekaCurlClient
from recommendation_contents.services.eureka_token import TokenCheckResult, TokenRefreshResult
from recommendation_contents.workflow_execution import execute_tasks, read_run, write_run

ROOT = Path(__file__).resolve().parents[1]


class Model:
    def __init__(self, broken_stage="", once=False):
        self.calls = []
        self.broken_stage = broken_stage
        self.once = once
        self.broke = False

    def invoke(self, messages):
        request = json.loads(messages[1]["content"])
        stage = "summary" if "briefs" in request else "topic"
        self.calls.append((stage, messages))
        if self.broken_stage == stage and not (self.once and self.broke):
            self.broke = True
            return '{"unexpected":"bad result"}'
        if stage == "topic":
            name = (
                "example-chip-interconnect-variants.json"
                if request["count"] == 2
                else "example-chip-interconnect.json"
            )
            return (ROOT / "docs/recommendation-tags/v2" / name).read_text()
        return json.dumps(
            {
                "research_prompts": [
                    {
                        "brief_id": brief["brief_id"],
                        "content_category": "scout_report",
                        "research_instructions": "Compare the routes against shared criteria; include an evidence table, limitations, and practical selection guidance.",
                    }
                    for brief in request["briefs"]
                ]
            }
        )


class Auth:
    def __init__(self, ready=True, expired=False):
        self.ready, self.expired, self.refreshes = ready, expired, 0

    def check_token(self):
        return TokenCheckResult(
            status="needs_refresh" if self.expired else ("ready" if self.ready else "missing"),
            reason="test",
            source="test",
            refresh_available=self.expired,
            authorization="Bearer test" if self.ready and not self.expired else "",
        )

    def refresh_access_token(self):
        self.expired = False
        self.ready = True
        self.refreshes += 1
        return TokenRefreshResult(
            success=True, status="refreshed", reason="test", authorization="Bearer test"
        )


class Client(EurekaCurlClient):
    def __init__(self, settings, responses=None):
        super().__init__(settings)
        self.responses = list(responses or [])
        self.queries, self.shares, self.polls = [], [], []
        self.submission = None
        self.on_submit = None

    def create_conversation(self, query):
        self.queries.append(query)
        if self.on_submit:
            self.on_submit()
        if isinstance(self.submission, Exception):
            raise self.submission
        return self.submission or CurlResult(
            {}, json.dumps({"session_id": f"sess_{len(self.queries)}"}), 200, 0
        )

    def create_share(self, session_id):
        self.shares.append(session_id)
        return CurlResult({}, json.dumps({"data": {"share_id": f"share_{session_id}"}}), 200, 0)

    def get_completion_status(self, session_id, cursor=""):
        self.polls.append((session_id, cursor))
        body = (
            self.responses.pop(0)
            if self.responses
            else {
                "status": "completed",
                "events": [{"type": "answer", "content": "Generated result"}],
            }
        )
        return body if isinstance(body, CurlResult) else CurlResult({}, json.dumps(body), 200, 0)


def setup(tmp_path, model=None, responses=None, auth=None, no_journal=False, checkpointer=None):
    settings = AppSettings(
        openai=OpenAISettings(api_key="test"),
        eureka=EurekaSettings(authorization="Bearer test", completion_timeout_seconds=0),
    )
    model = model or Model()
    client = Client(settings.eureka, responses)
    graph = build_graph_with_dependencies(
        settings=settings,
        llm=model,
        eureka_client=client,
        eureka_token_manager=auth or Auth(),
        runs_dir=None if no_journal else tmp_path,
        checkpointer=checkpointer,
    )
    return graph, model, client


def execution_setup(tmp_path, responses=None):
    settings = AppSettings(
        openai=OpenAISettings(api_key="test"),
        eureka=EurekaSettings(authorization="Bearer test", completion_timeout_seconds=0),
    )
    client = Client(settings.eureka, responses)
    runtime = RuntimeDependencies(
        settings=settings,
        eureka_client=client,
        eureka_token_manager=Auth(),
    )
    generation = {"generation_id": "generation-test", "input": {"idea": "test"}}
    specs = [
        {
            "brief_id": "00000000-0000-4000-8000-000000000001",
            "generated_prompt": "Generate the reviewed research deliverable.",
        }
    ]
    return runtime, client, generation, specs, tmp_path / "execution.json"


def test_only_three_nodes_and_two_generation_calls(tmp_path):
    graph, model, client = setup(tmp_path)
    assert set(graph.get_graph().nodes) == {
        "__start__",
        "generate_topic",
        "generate_research_prompt",
        "call_curl_task",
        "__end__",
    }
    assert {(e.source, e.target) for e in graph.get_graph().edges} == {
        ("__start__", "generate_topic"),
        ("generate_topic", "generate_research_prompt"),
        ("generate_research_prompt", "call_curl_task"),
        ("call_curl_task", "__end__"),
    }
    result = graph.invoke({"topic": "芯片互连", "language": "en"})
    assert [stage for stage, _ in model.calls] == ["topic", "summary"]
    assert result["status"] == "succeeded"
    assert result["generated_prompt"] == client.queries[0]
    assert result["generated_prompt"].endswith(HTML_INSTRUCTION)
    assert "in English" in result["generated_prompt"]
    assert result["results"][0]["isCompleted"] is True
    assert result["results"][0]["completion_response"]["events"]
    assert result["generation_result"]["briefs"][0] == result["task_specs"][0]["brief"]
    row = result["result_table_rows"][0]
    assert row["role"] == "rd_engineer"
    assert row["jtbd"] == '["technical_solutions"]'
    assert json.loads(row["tags"])["role_perspective"] == "product_design"
    assert row["status"] == "completed"
    assert Path(result["run_record_path"]).exists()


def test_submit_intent_and_session_are_saved_before_waiting(tmp_path):
    graph, _, client = setup(tmp_path)

    def before_submit():
        saved = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert saved["results"][0]["status"] == "submitting"

    client.on_submit = before_submit
    original_poll = client.get_completion_status

    def poll(session_id, cursor=""):
        saved = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert saved["results"][0]["session_id"] == session_id
        return original_poll(session_id, cursor)

    client.get_completion_status = poll
    graph.invoke({"topic": "芯片互连"})


def test_batch_keeps_two_llm_calls_and_separate_sessions(tmp_path):
    graph, model, client = setup(tmp_path)
    result = graph.invoke({"idea": "芯片互连", "count": 2, "format": "report"})
    assert len(model.calls) == 2
    assert len(client.queries) == 2
    assert all(HTML_INSTRUCTION not in query for query in client.queries)
    assert all(query.endswith(REPORT_INSTRUCTION) for query in client.queries)
    assert {r["session_id"] for r in result["results"]} == {"sess_1", "sess_2"}
    assert len({r["brief_id"] for r in result["results"]}) == 2


@pytest.mark.parametrize(
    "input_data", [{"topic": " "}, {"topic": "x", "count": 11}, {"topic": "x", "format": "pdf"}]
)
def test_invalid_input_stops_before_model_and_curl(tmp_path, input_data):
    graph, model, client = setup(tmp_path)
    with pytest.raises(GenerationError, match="generate_topic"):
        graph.invoke(input_data)
    assert model.calls == [] and client.queries == []


@pytest.mark.parametrize("stage", ["topic", "summary"])
def test_one_repair_stays_inside_its_generation_node(tmp_path, stage):
    graph, model, client = setup(tmp_path, Model(stage, once=True))
    assert graph.invoke({"topic": "芯片互连"})["status"] == "succeeded"
    assert len(model.calls) == 3 and len(client.queries) == 1


@pytest.mark.parametrize("stage", ["topic", "summary"])
def test_failed_generation_never_reaches_curl(tmp_path, stage):
    graph, _, client = setup(tmp_path, Model(stage))
    error_stage = "generate_research_prompt" if stage == "summary" else "generate_topic"
    with pytest.raises(GenerationError, match=error_stage):
        graph.invoke({"topic": "芯片互连"})
    assert client.queries == []


def test_auth_failure_returns_resumable_record_without_curl(tmp_path):
    graph, _, client = setup(tmp_path, auth=Auth(ready=False))
    result = graph.invoke({"topic": "芯片互连"})
    assert result["status"] == "failed"
    assert result["results"][0]["status"] == "needs_auth"
    assert client.queries == []
    assert Path(result["run_record_path"]).exists()


def test_auth_refresh_is_inside_curl_node(tmp_path):
    auth = Auth(expired=True)
    graph, _, client = setup(tmp_path, auth=auth)
    assert graph.invoke({"topic": "芯片互连"})["status"] == "succeeded"
    assert auth.refreshes == 1 and len(client.queries) == 1


def test_wait_limit_preserves_session_and_resume_skips_both_generations(tmp_path):
    graph, model, client = setup(tmp_path, responses=[{"status": "running"}])
    result = graph.invoke({"topic": "芯片互连"})
    assert result["status"] == "pending"
    run_id = result["generation_result"]["generation_id"]
    resumed = graph.invoke({"resume_run_id": run_id})
    assert resumed["status"] == "succeeded"
    assert len(model.calls) == 2 and len(client.queries) == 1 and len(client.shares) == 1
    assert resumed["session_id"] == result["session_id"]


def test_submit_only_then_completion_resume_reuses_session_and_share(tmp_path):
    runtime, client, generation, specs, path = execution_setup(tmp_path)

    submitted, status = execute_tasks(
        generation, specs, runtime, path, wait_for_completion=False
    )
    assert status == "pending"
    assert submitted[0]["status"] == "submitted"
    assert submitted[0]["session_id"] and submitted[0]["share_id"]
    assert len(client.queries) == 1 and len(client.shares) == 1 and client.polls == []

    completed, status = execute_tasks(
        generation, specs, runtime, path, wait_for_completion=True
    )
    assert status == "succeeded"
    assert completed[0]["status"] == "completed"
    assert len(client.queries) == 1 and len(client.shares) == 1 and len(client.polls) == 1


def test_uncertain_share_is_recorded_and_never_recreated(tmp_path):
    runtime, client, generation, specs, path = execution_setup(tmp_path)

    def interrupted_share(session_id):
        client.shares.append(session_id)
        raise RuntimeError("lost share response")

    client.create_share = interrupted_share
    submitted, _ = execute_tasks(generation, specs, runtime, path, wait_for_completion=False)
    assert submitted[0]["session_id"]
    assert submitted[0]["share_status"] == "submission_unknown"
    assert "verify" in submitted[0]["share_error"]
    assert len(client.queries) == 1 and len(client.shares) == 1

    submitted_again, _ = execute_tasks(
        generation, specs, runtime, path, wait_for_completion=False
    )
    assert submitted_again[0]["share_status"] == "submission_unknown"
    assert len(client.queries) == 1 and len(client.shares) == 1


def test_persisted_submitting_state_becomes_durable_unknown_without_resubmit(tmp_path):
    runtime, client, generation, specs, path = execution_setup(tmp_path)
    result = {
        "brief_id": specs[0]["brief_id"],
        "status": "submitting",
        "session_id": "",
        "session_url": "",
        "share_id": "",
        "share_url": "",
        "share_status": "pending",
        "isCompleted": False,
        "completion_status": "",
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

    resumed, _ = execute_tasks(generation, specs, runtime, path, wait_for_completion=False)
    assert resumed[0]["status"] == "submission_unknown"
    assert read_run(path)["results"][0]["status"] == "submission_unknown"
    assert client.queries == []


@pytest.mark.parametrize("reply", [CurlResult({}, "{}", 200, 0), RuntimeError("lost response")])
def test_ambiguous_submission_is_never_automatically_repeated(tmp_path, reply):
    graph, model, client = setup(tmp_path)
    client.submission = reply
    result = graph.invoke({"topic": "芯片互连"})
    assert result["results"][0]["status"] == "submission_unknown"
    graph.invoke({"resume_run_id": result["generation_result"]["generation_id"]})
    assert len(client.queries) == 1 and len(model.calls) == 2


def test_completion_pagination_does_not_resubmit(tmp_path):
    graph, _, client = setup(
        tmp_path,
        responses=[
            {
                "status": "completed",
                "has_more": True,
                "stream_cursor": "next",
                "events": [{"type": "start"}],
            },
            {"status": "completed", "has_more": False, "events": [{"type": "answer"}]},
        ],
    )
    result = graph.invoke({"topic": "芯片互连"})
    assert result["status"] == "succeeded"
    assert client.polls == [("sess_1", ""), ("sess_1", "next")]
    assert len(result["results"][0]["completion_response"]["events"]) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"status": "running", "events": [{"type": "tool_call", "status": "completed"}]},
        {"status": True, "events": [{"type": "tool_call", "status": "completed"}]},
    ],
)
def test_tool_or_transport_success_is_not_report_completion(tmp_path, body):
    graph, _, _ = setup(tmp_path, responses=[body])
    result = graph.invoke({"topic": "芯片互连"})
    assert result["status"] == "pending"
    assert result["results"][0]["isCompleted"] is False


def test_report_failure_is_returned_with_original_tags(tmp_path):
    graph, _, _ = setup(
        tmp_path,
        responses=[
            {
                "status": "failed",
                "events": [{"type": "error", "message": "Report generation failed"}],
            }
        ],
    )
    result = graph.invoke({"topic": "芯片互连"})
    assert result["status"] == "failed"
    assert result["result_table_rows"][0]["role"] == "rd_engineer"
    assert "Report generation failed" in result["errors"]


def test_tampered_resume_prompt_is_rejected(tmp_path):
    graph, _, client = setup(tmp_path, responses=[{"status": "running"}])
    result = graph.invoke({"topic": "芯片互连"})
    path = Path(result["run_record_path"])
    saved = json.loads(path.read_text())
    saved["task_specs"][0]["generated_prompt"] = "different prompt"
    path.write_text(json.dumps(saved))
    with pytest.raises(GenerationError):
        graph.invoke({"resume_run_id": result["generation_result"]["generation_id"]})
    assert len(client.queries) == 1


def test_cli_writes_all_batch_rows_and_preserves_tags(tmp_path, monkeypatch, capsys):
    import recommendation_contents.main as module

    graph, _, _ = setup(tmp_path / "runs")
    monkeypatch.setattr(module, "apply_env_file_to_process", lambda _: None)
    monkeypatch.setattr(module.AppSettings, "from_env_file", lambda _: None)
    monkeypatch.setattr(module, "build_graph_with_dependencies", lambda **kwargs: graph)
    csv_path = tmp_path / "results.csv"
    assert (
        module.main(
            [
                "芯片互连",
                "--count",
                "2",
                "--output",
                "json",
                "--records-csv",
                str(csv_path),
                "--records-md",
                str(tmp_path / "results.md"),
            ]
        )
        == 0
    )
    import csv

    with csv_path.open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert rows[0]["brief_id"] != rows[1]["brief_id"]
    assert json.loads(rows[1]["tags"])["role_perspective"] == "reliability_engineering"
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"


def test_resumed_record_updates_instead_of_counting_as_new_content(tmp_path):
    from recommendation_contents.records import read_csv_rows, save_result_table

    graph, _, _ = setup(tmp_path / "runs", responses=[{"status": "running"}])
    first = graph.invoke({"topic": "芯片互连"})
    csv_path = str(tmp_path / "records.csv")
    save_result_table(first["result_table_rows"][0], csv_path, "")
    resumed = graph.invoke({"resume_run_id": first["generation_result"]["generation_id"]})
    save_result_table(resumed["result_table_rows"][0], csv_path, "")
    rows = read_csv_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"


def test_stage_two_schema_is_exported_from_the_runtime_contract():
    from recommendation_contents.research_prompt_generation import (
        research_prompt_response_schema,
    )

    schema = research_prompt_response_schema()
    assert (
        json.loads((ROOT / "docs/workflows/research-prompt-response.schema.json").read_text())
        == schema
    )
    assert json.loads((ROOT / "docs/workflows/summary-response.schema.json").read_text()) == schema


def test_breakpoints_review_edit_and_continue_without_regenerating_topic(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    graph, model, client = setup(tmp_path, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "review"}}
    first = graph.invoke(
        {"topic": "芯片互连", "format": "report"},
        config=config,
        interrupt_after=["generate_topic"],
    )
    assert [stage for stage, _ in model.calls] == ["topic"]
    assert graph.get_state(config).next == ("generate_research_prompt",)
    assert client.queries == []
    assert not list(tmp_path.glob("*.json"))
    generation = copy.deepcopy(first["generation_result"])
    generation["briefs"][0]["description"] += "重点比较封装尺寸约束。"
    graph.update_state(config, {"generation_result": generation}, as_node="generate_topic")

    second = graph.invoke(None, config=config, interrupt_after=["generate_research_prompt"])
    assert [stage for stage, _ in model.calls] == ["topic", "summary"]
    request = json.loads(model.calls[-1][1][1]["content"])
    assert request["briefs"] == generation["briefs"]
    assert second["task_specs"][0]["brief"] == generation["briefs"][0]
    assert graph.get_state(config).next == ("call_curl_task",)
    assert client.queries == []

    final = graph.invoke(None, config=config)
    assert final["status"] == "succeeded"
    assert client.queries == [second["task_specs"][0]["generated_prompt"]]
    assert len(model.calls) == 2


def test_invalid_manual_topic_edit_stops_before_second_model_call(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    graph, model, client = setup(tmp_path, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "bad-edit"}}
    result = graph.invoke({"topic": "芯片互连"}, config, interrupt_after=["generate_topic"])
    generation = copy.deepcopy(result["generation_result"])
    generation["briefs"][0]["tags"]["role_perspective"] = "invented_tag"
    graph.update_state(config, {"generation_result": generation}, as_node="generate_topic")
    with pytest.raises(GenerationError, match="generate_research_prompt"):
        graph.invoke(None, config)
    assert len(model.calls) == 1
    assert client.queries == []


def test_manual_prompt_mismatch_stops_before_curl(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    graph, _, client = setup(tmp_path, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "bad-prompt"}}
    result = graph.invoke(
        {"topic": "芯片互连"},
        config,
        interrupt_after=["generate_research_prompt"],
    )
    specs = copy.deepcopy(result["task_specs"])
    specs[0]["generated_prompt"] = "mismatched metadata"
    graph.update_state(config, {"task_specs": specs}, as_node="generate_research_prompt")
    with pytest.raises(GenerationError, match="call_curl_task"):
        graph.invoke(None, config)
    assert client.queries == []


@pytest.mark.parametrize("wrapped", [False, True])
def test_import_first_stage_skips_topic_model_and_preserves_reviewed_content(tmp_path, wrapped):
    from recommendation_contents.brief_generation import generate_briefs

    generation = generate_briefs(
        {"idea": "芯片互连", "count": 2, "language": "en"}, lambda: Model()
    )
    generation["briefs"][0]["description"] += "重点比较封装尺寸约束。"
    stage = {"generation_result": generation, "format": "report"} if wrapped else generation
    graph, model, client = setup(tmp_path)
    result = graph.invoke({"stage_result": stage, "format": "report"})
    assert [stage for stage, _ in model.calls] == ["summary"]
    assert result["generation_result"] == generation
    assert result["format"] == "report"
    assert len(client.queries) == 2
    assert all("in English" in query for query in client.queries)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("schema_version", "unknown"),
        ("taxonomy_version", "old"),
        ("briefs", [None]),
        ("briefs", []),
        ("generation_id", "../bad"),
        ("input", None),
        ("generated_at", None),
    ],
)
def test_invalid_import_never_calls_models_or_curl(tmp_path, field, value):
    from recommendation_contents.brief_generation import generate_briefs

    generation = generate_briefs({"idea": "芯片互连"}, lambda: Model())
    generation[field] = value
    graph, model, client = setup(tmp_path)
    with pytest.raises(GenerationError, match="generate_topic"):
        graph.invoke({"stage_result": generation})
    assert model.calls == client.queries == []


def test_cli_review_files_continue_in_separate_processes(tmp_path, monkeypatch, capsys):
    import recommendation_contents.main as module

    graphs = []

    def factory(**kwargs):
        graph, model, client = setup(tmp_path / "runs", checkpointer=kwargs.get("checkpointer"))
        graphs.append((model, client))
        return graph

    monkeypatch.setattr(module, "apply_env_file_to_process", lambda _: None)
    monkeypatch.setattr(module.AppSettings, "from_env_file", lambda _: None)
    monkeypatch.setattr(module, "build_graph_with_dependencies", factory)
    first_path, second_path = tmp_path / "topic.json", tmp_path / "summary.json"
    assert (
        module.main(
            [
                "芯片互连",
                "--format",
                "report",
                "--stop-after",
                "generate_topic",
                "--stage-output",
                str(first_path),
                "--output",
                "json",
            ]
        )
        == 0
    )
    first = json.loads(first_path.read_text())
    assert first["status"] == "paused"
    assert json.loads(capsys.readouterr().out)["stopped_after"] == "generate_topic"
    assert [stage for stage, _ in graphs[0][0].calls] == ["topic"]
    assert graphs[0][1].queries == []
    first["generation_result"]["briefs"][0]["description"] += "重点比较封装尺寸约束。"
    first_path.write_text(json.dumps(first))

    assert (
        module.main(
            [
                "--from-stage-file",
                str(first_path),
                "--stop-after",
                "generate_research_prompt",
                "--stage-output",
                str(second_path),
                "--output",
                "json",
            ]
        )
        == 0
    )
    second = json.loads(second_path.read_text())
    assert (
        json.loads(capsys.readouterr().out)["stopped_after"]
        == "generate_research_prompt"
    )
    assert [stage for stage, _ in graphs[1][0].calls] == ["summary"]
    assert graphs[1][1].queries == []
    assert second["generation_result"] == first["generation_result"]
    assert second["format"] == "report"
    assert "重点比较封装尺寸约束" in second["generated_prompt"]
    assert not (tmp_path / "runs").exists()

    assert (
        module.main(
            [
                "--from-stage-file",
                str(second_path),
                "--output",
                "json",
                "--records-csv",
                str(tmp_path / "records.csv"),
                "--records-md",
                str(tmp_path / "records.md"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"
    assert graphs[2][0].calls == []
    assert graphs[2][1].queries == [second["task_specs"][0]["generated_prompt"]]


def test_cli_accepts_legacy_stage_two_name_but_saves_canonical_name(
    tmp_path, monkeypatch, capsys
):
    import recommendation_contents.main as module

    stage_path = tmp_path / "topic.json"
    stage_path.write_text("{}")
    output_path = tmp_path / "research-prompt.json"
    invocation = {}

    class Graph:
        def invoke(self, input_data, config=None, **kwargs):
            invocation.update(kwargs)
            return {"generation_result": {"generation_id": "test-generation"}}

    monkeypatch.setattr(module, "apply_env_file_to_process", lambda _: None)
    monkeypatch.setattr(module.AppSettings, "from_env_file", lambda _: None)
    monkeypatch.setattr(module, "build_graph_with_dependencies", lambda **_: Graph())

    assert (
        module.main(
            [
                "--from-stage-file",
                str(stage_path),
                "--stop-after",
                "generate_summary",
                "--stage-output",
                str(output_path),
                "--output",
                "json",
            ]
        )
        == 0
    )
    saved = json.loads(output_path.read_text())
    assert invocation["interrupt_after"] == ["generate_research_prompt"]
    assert saved["stopped_after"] == "generate_research_prompt"
    assert json.loads(capsys.readouterr().out)["stopped_after"] == "generate_research_prompt"


def test_former_stage_two_module_reexports_canonical_implementation():
    from recommendation_contents import research_prompt_generation as canonical
    from recommendation_contents import summary_generation as legacy

    assert legacy.generate_task_specs is canonical.generate_research_prompt_specs
    assert legacy.summary_response_schema is canonical.research_prompt_response_schema
    assert legacy.validate_summaries is canonical.validate_research_prompts
