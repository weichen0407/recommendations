import json

from recommendation_contents.config import AppSettings, EurekaSettings, OpenAISettings
from recommendation_contents.nodes import RuntimeDependencies
from recommendation_contents.services.eureka_curl import CurlResult, EurekaCurlClient
from recommendation_contents.services.eureka_token import TokenCheckResult
from recommendation_contents.workflow_execution import execute_tasks, write_run


class ReadyToken:
    def check_token(self):
        return TokenCheckResult(
            status="ready",
            reason="test",
            authorization="Bearer test",
            source="test",
        )


class Client(EurekaCurlClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.queries = []
        self.shares = []
        self.polls = []

    def create_conversation(self, query):
        self.queries.append(query)
        return CurlResult({}, json.dumps({"session_id": "sess_test"}), 200, 0)

    def create_share(self, session_id):
        self.shares.append(session_id)
        return CurlResult({}, json.dumps({"share_id": "share_test"}), 200, 0)

    def get_completion_status(self, session_id, cursor=""):
        self.polls.append((session_id, cursor))
        return CurlResult({}, json.dumps({"status": "completed"}), 200, 0)


def _setup():
    settings = AppSettings(
        openai=OpenAISettings(),
        eureka=EurekaSettings(authorization="Bearer test", completion_timeout_seconds=0),
    )
    client = Client(settings.eureka)
    runtime = RuntimeDependencies(
        settings=settings,
        eureka_client=client,
        eureka_token_manager=ReadyToken(),
    )
    generation = {"generation_id": "source"}
    spec = {"brief_id": "brief", "generated_prompt": "Prompt to execute"}
    return generation, spec, runtime, client


def test_submit_only_creates_session_and_share_without_completion_poll(tmp_path):
    generation, spec, runtime, client = _setup()
    path = tmp_path / "run.json"

    results, status = execute_tasks(
        generation, [spec], runtime, path, wait_for_completion=False
    )

    assert status == "pending"
    assert results[0]["status"] == "submitted"
    assert results[0]["session_id"] == "sess_test"
    assert results[0]["share_id"] == "share_test"
    assert results[0]["errors"] == []
    assert client.queries == ["Prompt to execute"]
    assert client.shares == ["sess_test"]
    assert client.polls == []

    execute_tasks(generation, [spec], runtime, path, wait_for_completion=False)
    assert client.queries == ["Prompt to execute"]
    assert client.shares == ["sess_test"]


def test_interrupted_share_is_not_retried_but_completion_can_continue(tmp_path):
    generation, spec, runtime, client = _setup()
    path = tmp_path / "run.json"
    write_run(
        path,
        {
            "workflow_version": "2.0.0",
            "generation_result": generation,
            "task_specs": [spec],
            "results": [
                {
                    "brief_id": "brief",
                    "status": "submitted",
                    "session_id": "sess_existing",
                    "session_url": "https://example/session",
                    "share_id": "",
                    "share_url": "",
                    "share_status": "submitting",
                    "isCompleted": False,
                    "completion_status": "",
                    "errors": [],
                }
            ],
        },
    )

    submitted, _ = execute_tasks(
        generation, [spec], runtime, path, wait_for_completion=False
    )
    assert submitted[0]["status"] == "submitted"
    assert submitted[0]["share_status"] == "submission_unknown"
    assert submitted[0]["errors"]
    assert client.queries == [] and client.shares == [] and client.polls == []

    completed, _ = execute_tasks(generation, [spec], runtime, path, wait_for_completion=True)
    assert completed[0]["status"] == "completed"
    assert completed[0]["isCompleted"] is True
    assert client.shares == []
    assert client.polls == [("sess_existing", "")]
