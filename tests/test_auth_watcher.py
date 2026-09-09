import base64
import json
import time

from recommendation_contents.auth_watcher import (
    build_cookie_header,
    extract_best_jwt_from_storage_entries,
    imported_auth_from_request,
    imported_auth_from_storage_entries,
    should_save_auth_candidate,
    signature_id_from_cookie_header,
)
from recommendation_contents.services.eureka_token import ImportedCurlAuth


def test_imported_auth_from_request_reads_case_insensitive_headers():
    token = _jwt_with_exp(time.time() + 600)

    candidate = imported_auth_from_request(
        "https://eureka-service.patsnap.com/api/eureka/query/conversational",
        {
            "Authorization": f"Bearer {token}",
            "X-Signature-Id": "pt_abc",
            "X-Site-Lang": "CN",
        },
        fallback_cookie="SESSION=session-id",
    )

    assert candidate is not None
    assert candidate.authorization == f"Bearer {token}"
    assert candidate.signature_id == "pt_abc"
    assert candidate.site_lang == "CN"
    assert candidate.cookie == "SESSION=session-id"
    assert candidate.expires_at == _jwt_exp(token)


def test_extract_best_jwt_from_storage_entries_chooses_latest_unexpired_token():
    older_token = _jwt_with_exp(time.time() + 60)
    newer_token = _jwt_with_exp(time.time() + 600)

    token, expires_at = extract_best_jwt_from_storage_entries(
        [
            {"store": "localStorage", "key": "old", "value": f'{{"token":"{older_token}"}}'},
            {"store": "localStorage", "key": "new", "value": f"Bearer {newer_token}"},
        ],
        min_expires_at=time.time(),
    )

    assert token == newer_token
    assert expires_at == _jwt_exp(newer_token)


def test_imported_auth_from_storage_entries_uses_cookie_and_signature_context():
    token = _jwt_with_exp(time.time() + 600)

    candidate = imported_auth_from_storage_entries(
        [{"store": "localStorage", "key": "accessToken", "value": token}],
        cookie_header="visitor_id=pt_cookie; SESSION=session-id",
        signature_id="pt_cookie",
        site_lang="CN",
        source_url="browser-storage:https://eureka.patsnap.com/",
        min_expires_at=time.time(),
    )

    assert candidate is not None
    assert candidate.authorization == f"Bearer {token}"
    assert candidate.signature_id == "pt_cookie"
    assert candidate.cookie == "visitor_id=pt_cookie; SESSION=session-id"
    assert candidate.source_url.startswith("browser-storage:")


def test_build_cookie_header_and_signature_id_from_cookie_header():
    cookie_header = build_cookie_header(
        [
            {"name": "visitor_id", "value": "pt_abc"},
            {"name": "SESSION", "value": "session-id"},
            {"name": "SESSION", "value": "session-id"},
        ]
    )

    assert cookie_header == "visitor_id=pt_abc; SESSION=session-id"
    assert signature_id_from_cookie_header(cookie_header) == "pt_abc"


def test_should_save_auth_candidate_rejects_older_access_token():
    current_token = _jwt_with_exp(time.time() + 600)
    older_token = _jwt_with_exp(time.time() + 60)

    should_save = should_save_auth_candidate(
        ImportedCurlAuth(
            authorization=f"Bearer {older_token}",
            signature_id="pt_new",
            expires_at=_jwt_exp(older_token),
        ),
        {
            "authorization": f"Bearer {current_token}",
            "signature_id": "pt_old",
            "site_lang": "CN",
            "cookie": "",
        },
    )

    assert should_save is False


def test_should_save_auth_candidate_accepts_new_signature_context():
    should_save = should_save_auth_candidate(
        ImportedCurlAuth(signature_id="pt_new"),
        {
            "authorization": "Bearer same",
            "signature_id": "pt_old",
            "site_lang": "CN",
            "cookie": "",
        },
    )

    assert should_save is True


def _jwt_with_exp(exp: float) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode("utf-8"))
    encoded_header = header.decode("utf-8").rstrip("=")
    payload = json.dumps({"exp": exp}).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    return f"{encoded_header}.{encoded_payload}.signature"


def _jwt_exp(token: str) -> float:
    payload = token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload + padding))["exp"]
