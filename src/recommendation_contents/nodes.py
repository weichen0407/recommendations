"""Shared runtime/auth helpers and the retained batch execution operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import AppSettings
from .dates import today_iso
from .llm import create_chat_model
from .onboarding_fields import (
    onboarding_industry_value,
    onboarding_jtbd_values,
    onboarding_role_value,
)
from .records import build_markdown_table
from .services.eureka_curl import EurekaCurlClient, find_first_value, parse_json_body
from .services.eureka_token import EurekaTokenManager
from .state import TopicWorkflowState


@dataclass
class RuntimeDependencies:
    settings: AppSettings
    llm: Any | None = None
    eureka_client: EurekaCurlClient | None = None
    eureka_token_manager: EurekaTokenManager | None = None

    def get_llm(self) -> Any:
        if self.llm is None:
            self.llm = create_chat_model(self.settings.openai)
        return self.llm

    def get_eureka_client(self) -> EurekaCurlClient:
        if self.eureka_client is None:
            self.eureka_client = EurekaCurlClient(self.settings.eureka)
        return self.eureka_client

    def get_eureka_token_manager(self) -> EurekaTokenManager:
        if self.eureka_token_manager is None:
            self.eureka_token_manager = EurekaTokenManager(self.settings.eureka)
        return self.eureka_token_manager


def check_user_token(state: TopicWorkflowState, runtime: RuntimeDependencies) -> dict[str, Any]:
    token_manager = runtime.get_eureka_token_manager()
    check_result = token_manager.check_token()
    client = runtime.get_eureka_client()

    if check_result.authorization:
        client.set_authorization(check_result.authorization)
    else:
        client.set_authorization("")
    if check_result.signature_id:
        client.set_signature_id(check_result.signature_id)
    if check_result.site_lang:
        client.set_site_lang(check_result.site_lang)
    if check_result.cookie:
        client.set_cookie(check_result.cookie)

    return {
        "token_status": check_result.status,
        "token_reason": check_result.reason,
        "token_refresh_available": check_result.refresh_available,
        "token_source": check_result.source,
        "debug": {
            **(state.get("debug") or {}),
            "token_checked": True,
            "token_status": check_result.status,
            "token_source": check_result.source,
            "token_refresh_available": check_result.refresh_available,
            "signature_id_loaded": bool(check_result.signature_id),
            "cookie_loaded": bool(check_result.cookie),
        },
    }


def refresh_user_token(state: TopicWorkflowState, runtime: RuntimeDependencies) -> dict[str, Any]:
    refresh_result = runtime.get_eureka_token_manager().refresh_access_token()
    errors = list(state.get("errors") or [])

    if refresh_result.success:
        runtime.get_eureka_client().set_authorization(refresh_result.authorization)
        errors = _remove_retryable_401_errors(errors)
    else:
        errors.append(f"Eureka token refresh failed: {refresh_result.reason}")

    return {
        "token_status": "ready" if refresh_result.success else "refresh_failed",
        "token_reason": refresh_result.reason,
        "token_refresh_attempted": True,
        "token_refresh_success": refresh_result.success,
        "token_refresh_error": "" if refresh_result.success else refresh_result.reason,
        "eureka_auth_status": "refreshed" if refresh_result.success else "refresh_failed",
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "token_refreshed": refresh_result.success,
            "token_refresh_status": refresh_result.status,
        },
    }


def call_curl_task(state: TopicWorkflowState, runtime: RuntimeDependencies) -> dict[str, Any]:
    client = runtime.get_eureka_client()
    generated_prompt = state.get("generated_prompt", "")
    errors = list(state.get("errors") or [])

    if not generated_prompt:
        errors.append("generated_prompt is empty")
        return {
            "curl_success": False,
            "curl_skipped": True,
            "eureka_auth_status": state.get("eureka_auth_status", ""),
            "errors": errors,
            "debug": {
                **(state.get("debug") or {}),
                "curl_task": "skipped: generated_prompt is empty",
            },
        }

    if not client.has_authorization_header():
        errors.append("EUREKA_AUTHORIZATION or EUREKA_BEARER_TOKEN is required for curl calls")
        return {
            "curl_success": False,
            "curl_skipped": True,
            "eureka_auth_status": "missing",
            "errors": errors,
            "debug": {
                **(state.get("debug") or {}),
                "curl_task": "skipped: missing authorization",
            },
        }

    query_result = client.create_conversation(generated_prompt)
    session_id = ""
    session_link = ""
    share_id = ""
    share_link = ""
    share_result = None

    if query_result.success:
        query_payload = parse_json_body(query_result.body)
        business_error = _eureka_business_error(query_payload)
        if business_error:
            errors.append(f"Eureka query returned business error: {business_error}")
        else:
            session_id = find_first_value(query_payload, {"session_id", "sessionId"})
            if session_id:
                session_link = client.build_session_link(session_id)
            else:
                errors.append("Eureka query response did not include session_id")
    else:
        errors.append(
            _curl_error_message(
                "Eureka query",
                query_result.return_code,
                query_result.status_code,
                query_result.stderr,
                query_result.body,
            )
        )

    if session_id:
        share_result = client.create_share(session_id)
        if share_result.success:
            share_payload = parse_json_body(share_result.body)
            business_error = _eureka_business_error(share_payload)
            if business_error:
                errors.append(f"Eureka share returned business error: {business_error}")
            else:
                share_id = find_first_value(share_payload, {"share_id", "shareId"})
                if share_id:
                    share_link = client.build_share_link(share_id)
                else:
                    errors.append("Eureka share response did not include share_id")
        else:
            errors.append(
                _curl_error_message(
                    "Eureka share",
                    share_result.return_code,
                    share_result.status_code,
                    share_result.stderr,
                    share_result.body,
                )
            )

    eureka_auth_status = _eureka_auth_status(
        query_result.status_code, share_result.status_code if share_result else 0
    )

    return {
        "curl_payload": query_result.payload,
        "curl_response": share_result.body if share_result else query_result.body,
        "curl_success": bool(session_id and share_id),
        "curl_skipped": False,
        "eureka_query_payload": query_result.payload,
        "eureka_query_response": query_result.body,
        "eureka_query_status_code": query_result.status_code,
        "eureka_query_return_code": query_result.return_code,
        "eureka_share_payload": share_result.payload if share_result else {},
        "eureka_share_response": share_result.body if share_result else "",
        "eureka_share_status_code": share_result.status_code if share_result else 0,
        "eureka_share_return_code": share_result.return_code if share_result else 0,
        "session_id": session_id,
        "session_link": session_link,
        "share_id": share_id,
        "share_link": share_link,
        "eureka_auth_status": eureka_auth_status,
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "curl_task": "called_eureka_query_and_share",
        },
    }


def route_after_token_check(state: TopicWorkflowState) -> str:
    if (
        state.get("token_status") == "needs_refresh"
        and state.get("token_refresh_available")
        and not state.get("token_refresh_attempted")
    ):
        return "refresh_user_token"
    return "call_curl_task"


def finalize_result(state: TopicWorkflowState) -> dict[str, Any]:
    rows = [
        {
            "input": state.get("topic", ""),
            "generated_prompt": state.get("generated_prompt", ""),
            "session_url": state.get("session_link", ""),
            "share_url": state.get("share_link", ""),
            "format": state.get("format", ""),
            "isCompleted": "",
            "completionStatus": "",
            "completionError": "",
            "title": state.get("title", ""),
            "categories": _csv_list(state.get("categories") or []),
            "keywords": _csv_list(state.get("keywords") or []),
            "description": state.get("description", ""),
            "role": onboarding_role_value(state.get("role", "")),
            "industry": onboarding_industry_value(state.get("industry", "")),
            "jtbd": _csv_list(onboarding_jtbd_values(state.get("jtbd") or [])),
            "date": state.get("date") or today_iso(),
            "sub_industry": _csv_list(state.get("sub_industry") or []),
        }
    ]

    return {
        "result_table_rows": rows,
        "result_table_markdown": build_markdown_table(rows),
        "debug": {
            **(state.get("debug") or {}),
            "finished": True,
        },
    }


def _curl_error_message(
    label: str,
    return_code: int,
    status_code: int,
    stderr: str,
    body: str = "",
) -> str:
    if return_code != 0:
        return f"{label} curl exited with code {return_code}: {stderr}"
    hint = _curl_response_hint(body)
    suffix = f": {hint}" if hint else ""
    return f"{label} returned HTTP {status_code}{suffix}"


def _curl_response_hint(body: str) -> str:
    payload = parse_json_body(body)
    if not isinstance(payload, dict):
        return ""

    for key in ("message", "error", "errcode", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _eureka_business_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    failed = payload.get("status") is False or payload.get("success") is False
    if not failed:
        return ""

    message = payload.get("message") or payload.get("error") or "request failed"
    code = payload.get("error_code") or payload.get("code")
    if code:
        return f"{message} (code={code})"
    return str(message)


def _eureka_auth_status(query_status_code: int, share_status_code: int) -> str:
    if query_status_code == 401 or share_status_code == 401:
        return "unauthorized"
    return "ready"


def _remove_retryable_401_errors(errors: list[str]) -> list[str]:
    retryable_messages = {
        "Eureka query returned HTTP 401",
        "Eureka share returned HTTP 401",
    }
    return [error for error in errors if error not in retryable_messages]


def _csv_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)
