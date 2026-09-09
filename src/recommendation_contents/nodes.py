"""LangGraph node implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import AppSettings
from .dates import today_iso
from .entities import (
    content_category_values,
    industry_values,
    jtbd_values,
    role_values,
    sub_industry_values,
)
from .llm import create_chat_model
from .prompts import build_prompt_generation_prompt, build_prompt_repair_prompt
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


def normalize_topic(state: TopicWorkflowState) -> dict[str, Any]:
    topic = (state.get("topic") or "").strip()
    context = state.get("request_context") or {}
    errors = list(state.get("errors") or [])

    if not topic:
        errors.append("topic is empty")

    return {
        "topic": topic,
        "request_context": context,
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "normalized": True,
        },
    }


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


def generate_prompt(state: TopicWorkflowState, runtime: RuntimeDependencies) -> dict[str, Any]:
    prompt = build_prompt_generation_prompt(state)
    response = runtime.get_llm().invoke(prompt)
    content = getattr(response, "content", str(response))
    metadata, errors = _parse_prompt_generation_response(content, state)
    repair_content = ""

    if not metadata["parsed_json"]:
        repair_prompt = build_prompt_repair_prompt(state, content)
        repair_response = runtime.get_llm().invoke(repair_prompt)
        repair_content = getattr(repair_response, "content", str(repair_response))
        repaired_metadata, repaired_errors = _parse_prompt_generation_response(repair_content, state)
        if repaired_metadata["parsed_json"]:
            metadata = repaired_metadata
            errors = list(state.get("errors") or [])
        else:
            errors = repaired_errors
            errors.append("generate_prompt repair did not return valid JSON")

    return {
        "prompt_generation_raw_response": content.strip(),
        "generated_prompt": metadata["generated_prompt"],
        "title": metadata["title"],
        "categories": metadata["categories"],
        "keywords": metadata["keywords"],
        "description": metadata["description"],
        "role": metadata["role"],
        "industry": metadata["industry"],
        "jtbd": metadata["jtbd"],
        "date": metadata["date"],
        "sub_industry": metadata["sub_industry"],
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "llm_model": runtime.settings.openai.model,
            "prompt_generated": True,
            "prompt_response_json": metadata["parsed_json"],
            "prompt_response_repaired": bool(repair_content and metadata["parsed_json"]),
            "prompt_repair_raw_response": repair_content.strip(),
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

    eureka_auth_status = _eureka_auth_status(query_result.status_code, share_result.status_code if share_result else 0)

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
            "title": state.get("title", ""),
            "categories": _csv_list(state.get("categories") or []),
            "keywords": _csv_list(state.get("keywords") or []),
            "description": state.get("description", ""),
            "role": state.get("role", ""),
            "industry": state.get("industry", ""),
            "jtbd": _csv_list(state.get("jtbd") or []),
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
        }
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


def _parse_prompt_generation_response(
    content: str,
    state: TopicWorkflowState,
) -> tuple[dict[str, Any], list[str]]:
    errors = list(state.get("errors") or [])
    payload = _parse_json_object(content)
    parsed_json = isinstance(payload, dict)

    if not parsed_json:
        errors.append("generate_prompt did not return valid JSON; using raw response as prompt")
        payload = {}

    topic = state.get("topic", "")
    generated_prompt = _string_value(payload.get("prompt")) or content.strip()
    title = _string_value(payload.get("title")) or topic
    metadata = {
        "generated_prompt": generated_prompt,
        "title": title,
        "categories": _enum_list(payload.get("categories"), content_category_values(), ["scout_report"]),
        "keywords": _string_list(payload.get("keywords")),
        "description": _string_value(payload.get("description")),
        "role": _enum_value(payload.get("role"), role_values(), "other"),
        "industry": _enum_value(payload.get("industry"), industry_values(), "other"),
        "jtbd": _enum_list(payload.get("jtbd"), jtbd_values(), ["other"]),
        "date": _string_value(payload.get("date")) or today_iso(),
        "sub_industry": _enum_list(payload.get("sub_industry"), sub_industry_values(), []),
        "parsed_json": parsed_json,
    }
    return metadata, errors


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = _strip_json_fence(content)
    payload = _loads_json_object(text)
    if payload is None:
        extracted = _extract_first_json_object(text)
        payload = _loads_json_object(extracted) if extracted else None
    return payload if isinstance(payload, dict) else None


def _loads_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _enum_value(value: Any, allowed: list[str], default: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return default


def _enum_list(value: Any, allowed: list[str], default: list[str]) -> list[str]:
    values = _string_list(value)
    filtered = []
    for item in values:
        if item in allowed and item not in filtered:
            filtered.append(item)
    return filtered or default


def _csv_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)
