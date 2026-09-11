"""Low-level curl contracts retained across the end-to-end graph migration."""

import json

from recommendation_contents.config import EurekaSettings
from recommendation_contents.services.eureka_curl import (
    EurekaCurlClient,
    build_curl_command,
    split_curl_output,
)


def test_build_curl_command_uses_argument_list():
    command = build_curl_command(
        url="https://example.test/task",
        headers={"Authorization": "Bearer token"},
        timeout_seconds=12,
        payload={"topic": "abc", "prompt": "def", "context": {}},
    )

    assert command[:4] == ["curl", "-sS", "--url", "https://example.test/task"]
    assert "Authorization: Bearer token" in command
    assert (
        command[command.index("--data-raw") + 1]
        == '{"topic": "abc", "prompt": "def", "context": {}}'
    )


def test_build_curl_command_omits_body_for_get():
    command = build_curl_command(
        url="https://example.test/status",
        headers={"Authorization": "Bearer token"},
        timeout_seconds=12,
        payload={"session_id": "sess_test"},
        method="GET",
    )

    assert command[:4] == [
        "curl",
        "-sS",
        "--url",
        "https://example.test/status?session_id=sess_test",
    ]
    assert "--data-raw" not in command
    assert command[command.index("--request") + 1] == "GET"


def test_completion_status_posts_limit_then_cursor(monkeypatch):
    calls = []

    class FakeCompletedProcess:
        stderr = ""
        returncode = 0
        stdout = '{"status":"running"}\n200'

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr("recommendation_contents.services.eureka_curl.subprocess.run", fake_run)
    client = EurekaCurlClient(
        EurekaSettings(
            authorization="Bearer token",
            completion_method="POST",
            completion_body={"cursor": "{cursor}", "limit": 500},
        )
    )

    client.get_completion_status("sess_test")
    client.get_completion_status("sess_test", cursor="archive:1788961829534-0")

    first_payload = json.loads(calls[0][calls[0].index("--data-raw") + 1])
    second_payload = json.loads(calls[1][calls[1].index("--data-raw") + 1])
    assert first_payload == {"limit": 500}
    assert second_payload == {"cursor": "archive:1788961829534-0", "limit": 500}


def test_split_curl_output_extracts_status_code():
    body, status = split_curl_output('{"ok":true}\n201')

    assert body == '{"ok":true}'
    assert status == 201
