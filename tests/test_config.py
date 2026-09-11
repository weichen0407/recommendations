import os

from recommendation_contents.config import (
    AppSettings,
    EurekaSettings,
    apply_env_file_to_process,
    load_env_file,
)


def test_load_env_file_parses_simple_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        OPENAI_MODEL="test-model"
        EUREKA_TIMEOUT_SECONDS=30
        """,
        encoding="utf-8",
    )

    values = load_env_file(str(env_file))

    assert values["OPENAI_MODEL"] == "test-model"
    assert values["EUREKA_TIMEOUT_SECONDS"] == "30"


def test_settings_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        OPENAI_API_KEY=secret
        OPENAI_BASE_URL=https://example.test/v1
        OPENAI_MODEL=model-a
        OPENAI_TEMPERATURE=1
        EUREKA_QUERY_ENDPOINT=https://query.test
        EUREKA_SHARE_ENDPOINT=https://share.test
        EUREKA_COMPLETION_ENDPOINT=https://completion.test/{session_id}
        EUREKA_COMPLETION_METHOD=POST
        EUREKA_COMPLETION_BODY_JSON={"session_id":"{session_id}"}
        EUREKA_COMPLETION_TIMEOUT_SECONDS=120
        EUREKA_COMPLETION_POLL_INTERVAL_SECONDS=3
        EUREKA_AUTHORIZATION=Bearer token
        EUREKA_SIGNATURE_ID=pt_test
        EUREKA_SITE_LANG=CN
        EUREKA_EXTRA_HEADERS_JSON={"X-Test-Eureka":"1"}
        EUREKA_TOKEN_CHECK_MODE=presence
        EUREKA_TOKEN_CACHE=/tmp/eureka-token.json
        EUREKA_TOKEN_REFRESH_ENABLED=true
        EUREKA_TOKEN_REFRESH_URL=https://refresh.test/token
        EUREKA_TOKEN_REFRESH_BODY_JSON={"refresh_token":"refresh"}
        """,
        encoding="utf-8",
    )

    settings = AppSettings.from_env_file(str(env_file))

    assert settings.openai.model == "model-a"
    assert settings.openai.base_url == "https://example.test/v1"
    assert settings.openai.temperature == 1.0
    assert settings.eureka.query_endpoint == "https://query.test"
    assert settings.eureka.share_endpoint == "https://share.test"
    assert settings.eureka.completion_endpoint == "https://completion.test/{session_id}"
    assert settings.eureka.completion_method == "POST"
    assert settings.eureka.completion_body == {"session_id": "{session_id}"}
    assert settings.eureka.completion_timeout_seconds == 120
    assert settings.eureka.completion_poll_interval_seconds == 3
    assert settings.eureka.authorization == "Bearer token"
    assert settings.eureka.signature_id == "pt_test"
    assert settings.eureka.extra_headers["X-Test-Eureka"] == "1"
    assert settings.eureka.token_check_mode == "presence"
    assert settings.eureka.token_cache == "/tmp/eureka-token.json"
    assert settings.eureka.token_refresh_enabled is True
    assert settings.eureka.token_refresh_url == "https://refresh.test/token"
    assert settings.eureka.token_refresh_body == {"refresh_token": "refresh"}


def test_apply_env_file_to_process_exports_langsmith_aliases(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        LANGSMITH_TRACING=false
        LANGSMITH_API_KEY=test-langsmith-key
        LANGSMITH_PROJECT=recommendation-contents
        """,
        encoding="utf-8",
    )
    for key in [
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
    ]:
        monkeypatch.delenv(key, raising=False)

    apply_env_file_to_process(str(env_file))

    assert os.environ["LANGSMITH_API_KEY"] == "test-langsmith-key"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    assert os.environ["LANGCHAIN_API_KEY"] == "test-langsmith-key"
    assert os.environ["LANGCHAIN_PROJECT"] == "recommendation-contents"


def test_apply_env_file_to_process_does_not_override_process_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LANGSMITH_PROJECT=from-file\n", encoding="utf-8")
    monkeypatch.setenv("LANGSMITH_PROJECT", "from-shell")
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)

    apply_env_file_to_process(str(env_file))

    assert os.environ["LANGSMITH_PROJECT"] == "from-shell"
    assert os.environ["LANGCHAIN_PROJECT"] == "from-shell"


def test_eureka_completion_defaults_match_events_endpoint():
    settings = EurekaSettings.from_env({})

    assert settings.completion_method == "POST"
    assert settings.completion_body == {"limit": 500}
