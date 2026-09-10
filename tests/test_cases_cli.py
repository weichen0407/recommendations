import base64
import json
import sys
import time

import pytest

from recommendation_contents import cases_cli
from recommendation_contents.cases_cli import (
    HTML_ARTIFACT_INSTRUCTION,
    apply_generation_mode,
    apply_mode_defaults,
    case_state_from_item,
    ensure_auth_ready,
    load_case_items,
    run_case_item,
)
from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    OpenAISettings,
    ProfileGateSettings,
)
from recommendation_contents.nodes import RuntimeDependencies
from recommendation_contents.services.eureka_curl import CurlResult
from recommendation_contents.services.eureka_token import EurekaTokenManager, TokenCheckResult


def test_load_case_items_reads_json_array_with_limit_and_offset(tmp_path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {"title": "one", "output": "prompt one"},
                {"title": "two", "output": "prompt two"},
                {"title": "three", "output": "prompt three"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    items = load_case_items(str(cases_path), offset=1, limit=2)

    assert items == [
        (1, {"title": "two", "output": "prompt two"}),
        (2, {"title": "three", "output": "prompt three"}),
    ]


def test_load_case_items_preserves_embedded_case_index(tmp_path):
    cases_path = tmp_path / "selection.json"
    cases_path.write_text(
        json.dumps(
            {
                "items": [
                    {"case_index": 67, "title": "selected one", "output": "prompt one"},
                    {"case_index": 120, "title": "selected two", "output": "prompt two"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    items = load_case_items(str(cases_path), offset=0, limit=2)

    assert items == [
        (67, {"case_index": 67, "title": "selected one", "output": "prompt one"}),
        (120, {"case_index": 120, "title": "selected two", "output": "prompt two"}),
    ]


def test_case_state_from_item_uses_output_as_generated_prompt():
    state = case_state_from_item(
        {
            "title": "Bazaarvoice, Inc.",
            "categories": ["competitor_analysis"],
            "keywords": ["saas", "patent portfolio"],
            "description": "A competitor analysis case.",
            "role": "innovation_product_strategy",
            "industry": "other",
            "jtbd": ["track_technologies_and_competitors"],
            "date": "2026-09-08",
            "sub_industry": ["general_strategy"],
            "output": "请生成结构化报告。",
        },
        case_index=0,
    )

    assert state["topic"] == "Bazaarvoice, Inc."
    assert state["generated_prompt"] == "请生成结构化报告。"
    assert state["categories"] == ["competitor_analysis"]
    assert state["jtbd"] == ["track_technologies_and_competitors"]
    assert state["errors"] == []


def test_case_state_from_item_parses_json_array_strings():
    state = case_state_from_item(
        {
            "title": "JSON arrays",
            "categories": '["case"]',
            "keywords": '["wearable", "digital health"]',
            "jtbd": '["identify_innovation_opportunities"]',
            "sub_industry": '["wearable_and_digital_health_devices"]',
            "output": "prompt",
        },
        case_index=0,
    )

    assert state["categories"] == ["case"]
    assert state["keywords"] == ["wearable", "digital health"]
    assert state["jtbd"] == ["identify_innovation_opportunities"]
    assert state["sub_industry"] == ["wearable_and_digital_health_devices"]


def test_apply_generation_mode_html_appends_artifact_instruction_once():
    item = {"title": "HTML", "output": "Write a report."}

    first = apply_generation_mode(item, "html")
    second = apply_generation_mode(first, "html")

    assert first["output"].endswith(HTML_ARTIFACT_INSTRUCTION)
    assert second["output"].count(HTML_ARTIFACT_INSTRUCTION) == 1
    assert item["output"] == "Write a report."


def test_apply_generation_mode_report_removes_artifact_instruction():
    item = {"title": "Report", "output": f"Write a report. {HTML_ARTIFACT_INSTRUCTION}"}

    result = apply_generation_mode(item, "report")

    assert result["output"] == "Write a report."


def test_apply_mode_defaults_uses_batch_folder_paths():
    args = type(
        "Args",
        (),
        {
            "mode": "html",
            "cases_json": "outputs/0910/091010/subject.json",
            "records_csv": "outputs/case_workflow_records.csv",
            "results_json": "outputs/case_workflow_results.json",
        },
    )()

    apply_mode_defaults(args, ["outputs/0910/091010/subject.json", "--mode", "html"])

    assert args.records_csv == "outputs/0910/091010/html/recommend_content_091010_html_records.csv"
    assert args.results_json == "/tmp/recommend_content_091010_html_results.json"


def test_main_stops_before_next_case_when_url_is_missing(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.json"
    env_path = tmp_path / ".env"
    records_path = tmp_path / "records.csv"
    results_path = tmp_path / "results.json"
    cases_path.write_text(
        json.dumps(
            [
                {"title": "first", "output": "prompt first"},
                {"title": "second", "output": "prompt second"},
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

    monkeypatch.setattr(cases_cli, "run_case_item", fake_run_case_item)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "case-workflow",
            str(cases_path),
            "--env-file",
            str(env_path),
            "--limit",
            "2",
            "--records-csv",
            str(records_path),
            "--results-json",
            str(results_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cases_cli.main()

    assert calls == [0]
    assert "stop before next case" in str(exc_info.value)
    assert not records_path.exists()
    assert json.loads(results_path.read_text(encoding="utf-8"))[0]["title"] == "first"


def test_run_case_item_retries_when_auth_cache_changes_after_401(tmp_path, monkeypatch):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "authorization": "Bearer old",
                "access_token": "old",
                "signature_id": "pt_old",
                "expires_at": time.time() + 600,
            }
        ),
        encoding="utf-8",
    )
    token_manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))
    client = FakeEurekaClient()
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(token_cache=str(cache_path)),
        ),
        eureka_client=client,
        eureka_token_manager=token_manager,
    )

    def update_auth(_seconds):
        cache_path.write_text(
            json.dumps(
                {
                    "authorization": "Bearer new",
                    "access_token": "new",
                    "signature_id": "pt_new",
                    "expires_at": time.time() + 600,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr("recommendation_contents.cases_cli.time.sleep", update_auth)

    result = run_case_item(
        case_index=0,
        item={"title": "case", "output": "prompt"},
        runtime=runtime,
        wait_on_401_seconds=1,
        retry_on_auth_change=True,
    )

    assert result["curl_success"] is True
    assert result["retry_count"] == 1
    assert result["session_id"] == "sess_retry"
    assert result["share_id"] == "share_retry"
    assert client.query_calls == 2


def test_run_case_item_can_import_clipboard_curl_during_401_wait(tmp_path, monkeypatch):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "authorization": "Bearer old",
                "access_token": "old",
                "signature_id": "pt_old",
                "expires_at": time.time() - 60,
            }
        ),
        encoding="utf-8",
    )
    token_manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))
    client = FakeEurekaClient()
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(token_cache=str(cache_path)),
        ),
        eureka_client=client,
        eureka_token_manager=token_manager,
    )
    new_token = _jwt_with_exp(time.time() + 600)

    class FakeClipboardProcess:
        returncode = 0
        stdout = (
            "curl --url 'https://eureka-service.patsnap.com/api/eureka/query/conversational' "
            f"-H 'authorization: Bearer {new_token}' "
            "-H 'x-signature-id: pt_new' "
            "-H 'x-site-lang: CN'"
        )

    monkeypatch.setattr(
        "recommendation_contents.cases_cli.subprocess.run",
        lambda *args, **kwargs: FakeClipboardProcess(),
    )

    result = run_case_item(
        case_index=0,
        item={"title": "case", "output": "prompt"},
        runtime=runtime,
        wait_on_401_seconds=1,
        retry_on_auth_change=True,
        import_clipboard_on_401=True,
        auth_poll_interval_seconds=0.1,
        allow_refresh=False,
    )

    assert result["curl_success"] is True
    assert result["retry_count"] == 1
    assert result["retry_events"][0]["clipboard_imported"] is True
    assert client.query_calls == 1


def test_run_case_item_can_skip_refresh_in_auth_import_mode():
    token_manager = FakeNeedsRefreshTokenManager()
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(),
        ),
        eureka_client=FakeEurekaClient(),
        eureka_token_manager=token_manager,
    )

    result = run_case_item(
        case_index=0,
        item={"title": "case", "output": "prompt"},
        runtime=runtime,
        retry_on_auth_change=True,
        allow_refresh=False,
    )

    assert token_manager.refresh_calls == 0
    assert result["curl_skipped"] is True
    assert result["eureka_auth_status"] == "needs_auth_update"
    assert "import a fresh browser curl" in result["errors"][0]


def test_ensure_auth_ready_waits_once_for_clipboard_import(tmp_path, monkeypatch):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "authorization": "Bearer old",
                "access_token": "old",
                "signature_id": "pt_old",
                "expires_at": time.time() - 60,
            }
        ),
        encoding="utf-8",
    )
    token_manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))
    runtime = RuntimeDependencies(
        settings=AppSettings(
            openai=OpenAISettings(),
            profile_gate=ProfileGateSettings(),
            eureka=EurekaSettings(token_cache=str(cache_path)),
        ),
        eureka_client=FakeEurekaClient(),
        eureka_token_manager=token_manager,
    )
    new_token = _jwt_with_exp(time.time() + 600)

    class FakeClipboardProcess:
        returncode = 0
        stdout = (
            "curl --url 'https://eureka-service.patsnap.com/api/eureka/query/conversational' "
            f"-H 'authorization: Bearer {new_token}' "
            "-H 'x-signature-id: pt_new' "
            "-H 'x-site-lang: CN'"
        )

    monkeypatch.setattr(
        "recommendation_contents.cases_cli.subprocess.run",
        lambda *args, **kwargs: FakeClipboardProcess(),
    )

    preflight = ensure_auth_ready(
        runtime=runtime,
        wait_on_401_seconds=1,
        import_clipboard_on_401=True,
        auth_poll_interval_seconds=0.1,
    )

    assert preflight["ready"] is True
    assert preflight["waited"] is True
    assert preflight["auth_changed"] is True
    assert preflight["clipboard_imported"] is True


class FakeNeedsRefreshTokenManager:
    def __init__(self):
        self.refresh_calls = 0

    def check_token(self):
        return TokenCheckResult(
            status="needs_refresh",
            reason="cached token expired",
            refresh_available=True,
            source="cache",
        )

    def refresh_access_token(self):
        self.refresh_calls += 1
        raise AssertionError("refresh should not be called in access import mode")

    def read_cached_auth_snapshot(self):
        return {
            "authorization": "Bearer old",
            "signature_id": "pt_old",
            "site_lang": "CN",
            "cookie": "",
        }


class FakeEurekaClient:
    def __init__(self):
        self.authorization = ""
        self.signature_id = ""
        self.cookie = ""
        self.query_calls = 0
        self.completion_calls = 0

    def has_authorization_header(self):
        return bool(self.authorization)

    def set_authorization(self, authorization):
        self.authorization = authorization

    def set_signature_id(self, signature_id):
        self.signature_id = signature_id

    def set_site_lang(self, _site_lang):
        return None

    def set_cookie(self, cookie):
        self.cookie = cookie

    def create_conversation(self, _query):
        self.query_calls += 1
        if self.authorization and self.authorization != "Bearer old" and self.signature_id == "pt_new":
            return CurlResult(
                payload={},
                body='{"session_id":"sess_retry"}',
                status_code=200,
                return_code=0,
            )
        return CurlResult(
            payload={},
            body='{"message":"Invalid signature"}',
            status_code=401,
            return_code=0,
        )

    def create_share(self, _session_id):
        return CurlResult(
            payload={},
            body='{"data":{"share_id":"share_retry"}}',
            status_code=200,
            return_code=0,
        )

    def has_completion_endpoint(self):
        return True

    def get_completion_status(self, _session_id):
        self.completion_calls += 1
        if self.completion_calls < 2:
            return CurlResult(
                payload={},
                body='{"data":{"status":"running"}}',
                status_code=200,
                return_code=0,
            )
        return CurlResult(
            payload={},
            body='{"data":{"completion":{"content":"done"}}}',
            status_code=200,
            return_code=0,
        )

    def build_session_link(self, session_id):
        return f"https://eureka.patsnap.com/ai-search/{session_id}"

    def build_share_link(self, share_id):
        return f"https://eureka.patsnap.com/share/?id={share_id}"


def _jwt_with_exp(exp: float) -> str:
    payload = json.dumps({"exp": exp}).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    return f"header.{encoded}.signature"
