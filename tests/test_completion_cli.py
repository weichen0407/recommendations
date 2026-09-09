import csv
import json

from recommendation_contents.completion_cli import (
    update_records_csv,
    update_usage_csv,
    validate_records_csv,
    validate_results,
)
from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    OpenAISettings,
    ProfileGateSettings,
)
from recommendation_contents.nodes import RuntimeDependencies
from recommendation_contents.services.eureka_curl import CurlResult


def test_validate_results_updates_completed_and_failed_sessions():
    results = [
        {
            "case_index": 1,
            "title": "done case",
            "session_id": "sess_done",
            "session_url": "https://eureka.test/sess_done",
            "share_url": "https://share.test/done",
            "errors": [],
            "row": {"session_url": "https://eureka.test/sess_done"},
        },
        {
            "case_index": 2,
            "title": "failed case",
            "session_id": "sess_failed",
            "session_url": "https://eureka.test/sess_failed",
            "share_url": "https://share.test/failed",
            "errors": [],
            "row": {"session_url": "https://eureka.test/sess_failed"},
        },
    ]
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(),
        ),
        eureka_client=FakeCompletionClient(),
    )

    updates = validate_results(results, runtime)

    assert [update.status for update in updates] == ["completed", "failed"]
    assert results[0]["isCompleted"] is True
    assert "isCompletion" not in results[0]
    assert "isComplete" not in results[0]
    assert results[0]["row"]["isCompleted"] == "true"
    assert "isCompletion" not in results[0]["row"]
    assert "isComplete" not in results[0]["row"]
    assert results[1]["isCompleted"] is False
    assert results[1]["completion_error"] == "bad artifact"
    assert results[1]["row"]["completionError"] == "bad artifact"
    assert results[1]["errors"] == ["Eureka session failed: bad artifact"]


def test_update_records_and_usage_csv(tmp_path):
    updates = validate_results(
        [
            {
                "case_index": 1,
                "title": "done case",
                "session_id": "sess_done",
                "session_url": "https://eureka.test/sess_done",
                "share_url": "https://share.test/done",
                "errors": [],
            },
            {
                "case_index": 2,
                "title": "failed case",
                "session_id": "sess_failed",
                "session_url": "https://eureka.test/sess_failed",
                "share_url": "https://share.test/failed",
                "errors": [],
            },
        ],
        RuntimeDependencies(
            settings=AppSettings(
                openai=OpenAISettings(),
                profile_gate=ProfileGateSettings(),
                eureka=EurekaSettings(),
            ),
            eureka_client=FakeCompletionClient(),
        ),
    )
    records_path = tmp_path / "records.csv"
    records_path.write_text(
        "input,session_url,share_url\n"
        "done,https://eureka.test/sess_done,https://share.test/done\n"
        "failed,https://eureka.test/sess_failed,https://share.test/failed\n",
        encoding="utf-8",
    )
    usage_path = tmp_path / "usage.csv"
    usage_path.write_text(
        "case_index,title,industry,status,session_url,share_url,error\n"
        "1,done case,automotive,used,https://eureka.test/sess_done,https://share.test/done,\n"
        "2,failed case,automotive,used,https://eureka.test/sess_failed,https://share.test/failed,\n",
        encoding="utf-8",
    )

    assert update_records_csv(str(records_path), updates) == 2
    assert update_usage_csv(str(usage_path), updates) == 2

    records = _read_csv(records_path)
    usage = _read_csv(usage_path)
    assert records[0]["isCompleted"] == "true"
    assert "isCompletion" not in records[0]
    assert "isComplete" not in records[0]
    assert records[1]["completionStatus"] == "failed"
    assert records[1]["completionError"] == "bad artifact"
    assert usage[0]["status"] == "used"
    assert usage[0]["isCompleted"] == "true"
    assert "isCompletion" not in usage[0]
    assert "isComplete" not in usage[0]
    assert usage[1]["status"] == "failed"
    assert usage[1]["error"] == "bad artifact"


def test_validate_records_csv_scans_session_urls(tmp_path):
    records_path = tmp_path / "records.csv"
    records_path.write_text(
        "input,session_url,share_url\n"
        "done,https://eureka.patsnap.com/ai-search/sess_done,https://share.test/done\n"
        "failed,https://eureka.patsnap.com/ai-search/sess_failed,https://share.test/failed\n",
        encoding="utf-8",
    )
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(),
        ),
        eureka_client=FakeCompletionClient(),
    )

    updates = validate_records_csv(str(records_path), runtime)

    records = _read_csv(records_path)
    assert [update.session_id for update in updates] == ["sess_done", "sess_failed"]
    assert records[0]["isCompleted"] == "true"
    assert "isCompletion" not in records[0]
    assert "isComplete" not in records[0]
    assert records[1]["isCompleted"] == "false"
    assert records[1]["completionStatus"] == "failed"
    assert records[1]["completionError"] == "bad artifact"


def test_validate_records_csv_migrates_legacy_completion_columns(tmp_path):
    records_path = tmp_path / "records.csv"
    records_path.write_text(
        "input,session_url,share_url,isComplete,completionStatus\n"
        "done,https://eureka.patsnap.com/ai-search/sess_done,https://share.test/done,true,completed\n",
        encoding="utf-8",
    )
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(),
        ),
        eureka_client=FakeCompletionClient(),
    )

    updates = validate_records_csv(str(records_path), runtime)

    records = _read_csv(records_path)
    assert updates == []
    assert records[0]["isCompleted"] == "true"
    assert "isComplete" not in records[0]
    assert "isCompletion" not in records[0]


class FakeCompletionClient:
    def has_completion_endpoint(self):
        return True

    def get_completion_status(self, session_id):
        if session_id == "sess_done":
            body = json.dumps({"events": [{"status": "running"}, {"status": "completed"}]})
        else:
            body = json.dumps(
                {
                    "events": [
                        {"status": "running"},
                        {"status": "failed"},
                        {"type": "error", "message": "bad artifact"},
                    ]
                }
            )
        return CurlResult(payload={}, body=body, status_code=200, return_code=0)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))
