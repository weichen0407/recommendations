import base64
import json
import time

from recommendation_contents.config import EurekaSettings
from recommendation_contents.services.eureka_token import EurekaTokenManager, parse_imported_curl


def test_save_refresh_credentials_writes_cache_without_access_token(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    saved_path = manager.save_refresh_credentials(
        refresh_token="refresh-token",
        cookie="SESSION=session-id",
        client_id="client-id",
    )

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved_path == cache_path
    assert data["refresh_token"] == "refresh-token"
    assert data["cookie"] == "SESSION=session-id"
    assert data["client_id"] == "client-id"
    assert data["from"] == "eureka"
    assert data["response_type"] == "TOKEN"
    assert "access_token" not in data
    assert "authorization" not in data


def test_refresh_body_uses_refresh_token_from_cache(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "refresh_token": "refresh-from-cache",
                "client_id": "client-from-cache",
                "from": "eureka",
                "response_type": "TOKEN",
            }
        ),
        encoding="utf-8",
    )
    manager = EurekaTokenManager(
        EurekaSettings(
            token_cache=str(cache_path),
            token_refresh_body={"from": "eureka", "response_type": "TOKEN"},
        )
    )

    body = manager._refresh_body(manager._read_cached_record())

    assert body == {
        "from": "eureka",
        "response_type": "TOKEN",
        "refresh_token": "refresh-from-cache",
        "client_id": "client-from-cache",
    }


def test_check_token_prefers_cache_when_settings_authorization_is_expired(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "access_token": "cached-access-token",
                "expires_at": time.time() + 600,
            }
        ),
        encoding="utf-8",
    )
    manager = EurekaTokenManager(
        EurekaSettings(
            authorization=f"Bearer {_jwt_with_exp(time.time() - 600)}",
            token_cache=str(cache_path),
            token_refresh_enabled=True,
            token_refresh_url="https://passport.example/token/refresh",
        )
    )

    result = manager.check_token()

    assert result.status == "ready"
    assert result.source == "cache"
    assert result.authorization == "Bearer cached-access-token"


def test_import_curl_saves_access_signature_site_lang_and_cookie(tmp_path):
    expires_at = time.time() + 600
    access_token = _jwt_with_exp(expires_at)
    cache_path = tmp_path / "eureka_token.json"
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    result = manager.import_curl(
        "\n".join(
            [
                "curl --url 'https://eureka-service.patsnap.com/api/eureka/query/conversational' \\",
                f"-H 'authorization: Bearer {access_token}' \\",
                "-H 'x-signature-id: pt_abc' \\",
                "-H 'x-site-lang: CN' \\",
                "-b 'DEVICE_ID=device-id; SESSION=session-id'",
            ]
        )
    )

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert result["has_authorization"] is True
    assert result["has_signature_id"] is True
    assert result["has_cookie"] is True
    assert data["authorization"] == f"Bearer {access_token}"
    assert data["access_token"] == access_token
    assert data["signature_id"] == "pt_abc"
    assert data["site_lang"] == "CN"
    assert data["cookie"] == "DEVICE_ID=device-id; SESSION=session-id"
    assert data["imported_from_url"].endswith("/api/eureka/query/conversational")
    assert float(data["expires_at"]) == expires_at


def test_import_auth_saves_browser_observation_without_printing_secrets(tmp_path):
    expires_at = time.time() + 600
    access_token = _jwt_with_exp(expires_at)
    cache_path = tmp_path / "eureka_token.json"
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    result = manager.import_auth(
        authorization=f"Bearer {access_token}",
        signature_id="pt_browser",
        site_lang="CN",
        cookie="SESSION=session-id",
        source_url="browser-request",
        expires_at=expires_at,
    )

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert result["has_authorization"] is True
    assert result["has_signature_id"] is True
    assert result["has_cookie"] is True
    assert access_token not in json.dumps(result)
    assert data["authorization"] == f"Bearer {access_token}"
    assert data["signature_id"] == "pt_browser"
    assert data["cookie"] == "SESSION=session-id"
    assert data["imported_from_url"] == "browser-request"


def test_parse_imported_curl_handles_markdown_links_and_escaped_underscores():
    parsed = parse_imported_curl(
        "curl --url '[https://example.test/a](https://example.test/a)' \\\n"
        "-H 'authorization: Bearer token_with\\_underscore' \\\n"
        "-H 'x-signature-id: pt\\_abc' \\\n"
        "-H 'x-site-lang: CN'"
    )

    assert parsed.authorization == "Bearer token_with_underscore"
    assert parsed.signature_id == "pt_abc"
    assert parsed.source_url == "https://example.test/a"


def test_save_cookie_preserves_existing_refresh_credentials(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(
        json.dumps(
            {
                "refresh_token": "refresh-token",
                "client_id": "client-id",
                "from": "eureka",
                "response_type": "TOKEN",
            }
        ),
        encoding="utf-8",
    )
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    saved_path = manager.save_cookie("SESSION=session-id")

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved_path == cache_path
    assert data["refresh_token"] == "refresh-token"
    assert data["client_id"] == "client-id"
    assert data["cookie"] == "SESSION=session-id"


def test_refresh_headers_use_cookie_from_cache(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    cache_path.write_text(json.dumps({"cookie": "SESSION=session-id"}), encoding="utf-8")
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    headers = manager._refresh_headers(manager._read_cached_record())

    assert headers["cookie"] == "SESSION=session-id"
    assert headers["accept"] == "application/json"


def test_token_record_parses_nested_refresh_response(tmp_path):
    cache_path = tmp_path / "eureka_token.json"
    manager = EurekaTokenManager(EurekaSettings(token_cache=str(cache_path)))

    record = manager._token_record_from_response(
        {
            "data": {
                "accessToken": "new-access-token",
                "refreshToken": "new-refresh-token",
                "expiresIn": 120,
            }
        },
        {
            "authorization": "Bearer old-access-token",
            "refresh_token": "old-refresh-token",
        },
    )

    assert record["authorization"] == "Bearer new-access-token"
    assert record["access_token"] == "new-access-token"
    assert record["refresh_token"] == "new-refresh-token"
    assert float(record["expires_at"]) > time.time()


def _jwt_with_exp(exp: float) -> str:
    payload = json.dumps({"exp": exp}).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    return f"header.{encoded}.signature"
