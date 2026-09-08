from recommendation_contents.config import AppSettings, load_env_file


def test_load_env_file_parses_simple_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        OPENAI_MODEL="test-model"
        PROFILE_GATE_RETRY_COUNT=3
        """,
        encoding="utf-8",
    )

    values = load_env_file(str(env_file))

    assert values["OPENAI_MODEL"] == "test-model"
    assert values["PROFILE_GATE_RETRY_COUNT"] == "3"


def test_settings_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        OPENAI_API_KEY=secret
        OPENAI_BASE_URL=https://example.test/v1
        OPENAI_MODEL=model-a
        OPENAI_TEMPERATURE=1
        PROFILE_GATE_ENDPOINT=https://profile.test
        PROFILE_GATE_EXTRA_HEADERS_JSON={"X-Test":"1"}
        EUREKA_QUERY_ENDPOINT=https://query.test
        EUREKA_SHARE_ENDPOINT=https://share.test
        EUREKA_AUTHORIZATION=Bearer token
        EUREKA_SIGNATURE_ID=pt_test
        EUREKA_SITE_LANG=CN
        EUREKA_EXTRA_HEADERS_JSON={"X-Test-Eureka":"1"}
        """,
        encoding="utf-8",
    )

    settings = AppSettings.from_env_file(str(env_file))

    assert settings.openai.model == "model-a"
    assert settings.openai.base_url == "https://example.test/v1"
    assert settings.openai.temperature == 1.0
    assert settings.profile_gate.endpoint == "https://profile.test"
    assert settings.profile_gate.extra_headers == {"X-Test": "1"}
    assert settings.eureka.query_endpoint == "https://query.test"
    assert settings.eureka.share_endpoint == "https://share.test"
    assert settings.eureka.authorization == "Bearer token"
    assert settings.eureka.signature_id == "pt_test"
    assert settings.eureka.extra_headers["X-Test-Eureka"] == "1"
