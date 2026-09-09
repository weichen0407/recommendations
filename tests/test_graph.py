import json

from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    OpenAISettings,
    ProfileGateSettings,
)
from recommendation_contents.graph import build_graph_with_dependencies
from recommendation_contents.services.eureka_curl import (
    build_curl_command,
    split_curl_output,
)
from recommendation_contents.services.eureka_token import TokenCheckResult, TokenRefreshResult


class FakeMessage:
    content = json.dumps(
        {
            "title": "新能源汽车电池回收趋势研究",
            "categories": ["scout_report"],
            "keywords": ["新能源汽车", "电池回收"],
            "description": "面向电池回收趋势的结构化研究报告。",
            "role": "innovation_product_strategy",
            "industry": "automotive",
            "jtbd": ["identify_innovation_opportunities"],
            "date": "2026-09-08",
            "sub_industry": ["ev_and_battery_systems"],
            "prompt": "请围绕主题完成一份结构化研究提示词。",
        },
        ensure_ascii=False,
    )


class Message:
    def __init__(self, content):
        self.content = content


class FakeLlm:
    def invoke(self, prompt):
        assert "新能源汽车电池回收趋势" in prompt
        return FakeMessage()


def test_topic_workflow_skips_curl_without_authorization():
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=FakeLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert result["topic"] == "新能源汽车电池回收趋势"
    assert result["generated_prompt"] == "请围绕主题完成一份结构化研究提示词。"
    assert result["title"] == "新能源汽车电池回收趋势研究"
    assert result["categories"] == ["scout_report"]
    assert result["token_status"] == "missing"
    assert result["curl_skipped"] is True
    assert result["result_table_rows"][0]["session_url"] == ""
    assert result["debug"]["finished"] is True


def test_topic_workflow_places_token_check_before_curl():
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=FakeLlm())

    edges = {(edge.source, edge.target, edge.conditional) for edge in graph.get_graph().edges}

    assert ("normalize_topic", "generate_prompt", False) in edges
    assert ("generate_prompt", "check_user_token", False) in edges
    assert ("check_user_token", "call_curl_task", True) in edges
    assert ("check_user_token", "refresh_user_token", True) in edges
    assert ("refresh_user_token", "check_user_token", False) in edges
    assert ("call_curl_task", "finalize_result", False) in edges
    assert ("normalize_topic", "check_user_token", False) not in edges
    assert ("call_curl_task", "refresh_user_token", True) not in edges
    assert ("refresh_user_token", "generate_prompt", True) not in edges


def test_topic_workflow_creates_eureka_links(monkeypatch):
    calls = []

    class FakeCompletedProcess:
        def __init__(self, stdout):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def fake_run(command, check, capture_output, text):
        assert check is False
        assert capture_output is True
        assert text is True
        calls.append(command)
        if any("conversational" in part for part in command):
            return FakeCompletedProcess('{"session_id":"sess_test"}\n200')
        return FakeCompletedProcess('{"data":{"share_id":"share_test"}}\n200')

    monkeypatch.setattr("recommendation_contents.services.eureka_curl.subprocess.run", fake_run)
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(authorization="Bearer token", signature_id="pt_test"),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=FakeLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert calls[0][calls[0].index("--data-raw") + 1].find("请围绕主题完成一份结构化研究提示词。") >= 0
    assert calls[1][calls[1].index("--data-raw") + 1].find("sess_test") >= 0
    assert result["session_id"] == "sess_test"
    assert result["share_id"] == "share_test"
    assert result["session_link"].startswith("https://eureka.patsnap.com/ai-search/sess_test")
    assert result["share_link"].startswith("https://eureka.patsnap.com/share/?id=share_test")
    assert result["result_table_rows"][0]["title"] == "新能源汽车电池回收趋势研究"
    assert result["result_table_rows"][0]["categories"] == '["scout_report"]'
    assert result["result_table_rows"][0]["jtbd"] == '["innovation_opportunities"]'
    assert "share_url" in result["result_table_markdown"]


def test_topic_workflow_reports_eureka_business_error(monkeypatch):
    class FakeCompletedProcess:
        stderr = ""
        returncode = 0
        stdout = (
            '{"status":false,"error_code":71000021,'
            '"message":"Insufficient credits: required 500"}\n200'
        )

    monkeypatch.setattr(
        "recommendation_contents.services.eureka_curl.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(authorization="Bearer token", signature_id="pt_test"),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=FakeLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert result["curl_success"] is False
    assert result["session_link"] == ""
    assert "Insufficient credits" in result["errors"][0]


def test_topic_workflow_refreshes_from_token_check_before_curl(monkeypatch):
    calls = []

    class FakeCompletedProcess:
        def __init__(self, stdout):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    class FakeTokenManager:
        def __init__(self):
            self.refresh_calls = 0
            self.check_calls = 0

        def check_token(self):
            self.check_calls += 1
            if self.refresh_calls == 0:
                return TokenCheckResult(
                    status="needs_refresh",
                    reason="token expired",
                    refresh_available=True,
                    source="cache",
                )
            return TokenCheckResult(
                status="ready",
                reason="new token",
                authorization="Bearer new",
                refresh_available=True,
                source="cache",
            )

        def refresh_access_token(self):
            self.refresh_calls += 1
            return TokenRefreshResult(
                success=True,
                status="refreshed",
                reason="new token",
                authorization="Bearer new",
            )

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        authorization = _header_value(command, "authorization")
        if any("conversational" in part for part in command):
            assert authorization == "Bearer new"
            return FakeCompletedProcess('{"session_id":"sess_after_refresh"}\n200')
        return FakeCompletedProcess('{"data":{"share_id":"share_after_refresh"}}\n200')

    token_manager = FakeTokenManager()
    monkeypatch.setattr("recommendation_contents.services.eureka_curl.subprocess.run", fake_run)
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(authorization="Bearer old", signature_id="pt_test"),
    )
    graph = build_graph_with_dependencies(
        settings=settings,
        llm=FakeLlm(),
        eureka_token_manager=token_manager,
    )

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert token_manager.refresh_calls == 1
    assert token_manager.check_calls == 2
    assert len([call for call in calls if any("conversational" in part for part in call)]) == 1
    assert _header_value(calls[0], "authorization") == "Bearer new"
    assert result["session_id"] == "sess_after_refresh"
    assert result["share_id"] == "share_after_refresh"
    assert result["token_refresh_success"] is True
    assert result["eureka_auth_status"] == "ready"


def test_topic_workflow_repairs_invalid_prompt_json():
    class RepairingLlm:
        def __init__(self):
            self.calls = 0

        def invoke(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return Message("请围绕主题完成一份结构化研究提示词。")
            return Message(FakeMessage.content)

    llm = RepairingLlm()
    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=llm)

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert llm.calls == 2
    assert result["debug"]["prompt_response_json"] is True
    assert result["debug"]["prompt_response_repaired"] is True
    assert "generate_prompt did not return valid JSON; using raw response as prompt" not in result["errors"]
    assert result["generated_prompt"] == "请围绕主题完成一份结构化研究提示词。"


def test_topic_workflow_extracts_json_from_wrapped_response():
    class WrappedJsonLlm:
        def invoke(self, prompt):
            return Message(f"好的，结果如下：\n```json\n{FakeMessage.content}\n```")

    settings = AppSettings(
        openai=OpenAISettings(api_key="test-key", model="test-model"),
        profile_gate=ProfileGateSettings(),
        eureka=EurekaSettings(),
    )
    graph = build_graph_with_dependencies(settings=settings, llm=WrappedJsonLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert result["debug"]["prompt_response_json"] is True
    assert result["debug"]["prompt_response_repaired"] is False
    assert result["title"] == "新能源汽车电池回收趋势研究"


def test_build_curl_command_uses_argument_list():
    command = build_curl_command(
        url="https://example.test/task",
        headers={"Authorization": "Bearer token"},
        timeout_seconds=12,
        payload={"topic": "abc", "prompt": "def", "context": {}},
    )

    assert command[:4] == ["curl", "-sS", "--url", "https://example.test/task"]
    assert "Authorization: Bearer token" in command
    assert command[command.index("--data-raw") + 1] == '{"topic": "abc", "prompt": "def", "context": {}}'


def test_split_curl_output_extracts_status_code():
    body, status = split_curl_output('{"ok":true}\n201')

    assert body == '{"ok":true}'
    assert status == 201


def _header_value(command, header_name):
    for index, item in enumerate(command):
        if item == "-H":
            key, _, value = command[index + 1].partition(":")
            if key.lower() == header_name.lower():
                return value.strip()
    return ""
