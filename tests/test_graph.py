from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    OpenAISettings,
    ProfileGateSettings,
)
from recommendation_contents.graph import build_graph
from recommendation_contents.services.eureka_curl import (
    build_curl_command,
    split_curl_output,
)


class FakeMessage:
    content = "请围绕主题完成一份结构化研究提示词。"


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
    graph = build_graph(settings=settings, llm=FakeLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert result["topic"] == "新能源汽车电池回收趋势"
    assert result["generated_prompt"] == "请围绕主题完成一份结构化研究提示词。"
    assert result["curl_skipped"] is True
    assert result["result_table_rows"][0]["session 会话链接"] == ""
    assert result["debug"]["finished"] is True


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
    graph = build_graph(settings=settings, llm=FakeLlm())

    result = graph.invoke({"topic": "新能源汽车电池回收趋势", "request_context": {}})

    assert calls[0][calls[0].index("--data-raw") + 1].find("请围绕主题完成一份结构化研究提示词。") >= 0
    assert calls[1][calls[1].index("--data-raw") + 1].find("sess_test") >= 0
    assert result["session_id"] == "sess_test"
    assert result["share_id"] == "share_test"
    assert result["session_link"].startswith("https://eureka.patsnap.com/ai-search/sess_test")
    assert result["share_link"].startswith("https://eureka.patsnap.com/share/?id=share_test")
    assert "最终分享链接" in result["result_table_markdown"]


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
