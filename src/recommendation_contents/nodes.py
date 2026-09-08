"""LangGraph node implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AppSettings
from .llm import create_chat_model
from .prompts import build_prompt_generation_prompt
from .services.eureka_curl import EurekaCurlClient, find_first_value, parse_json_body
from .state import TopicWorkflowState


@dataclass
class RuntimeDependencies:
    settings: AppSettings
    llm: Any | None = None
    eureka_client: EurekaCurlClient | None = None

    def get_llm(self) -> Any:
        if self.llm is None:
            self.llm = create_chat_model(self.settings.openai)
        return self.llm

    def get_eureka_client(self) -> EurekaCurlClient:
        if self.eureka_client is None:
            self.eureka_client = EurekaCurlClient(self.settings.eureka)
        return self.eureka_client


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


def generate_prompt(state: TopicWorkflowState, runtime: RuntimeDependencies) -> dict[str, Any]:
    prompt = build_prompt_generation_prompt(state)
    response = runtime.get_llm().invoke(prompt)
    content = getattr(response, "content", str(response))

    return {
        "generated_prompt": content.strip(),
        "debug": {
            **(state.get("debug") or {}),
            "llm_model": runtime.settings.openai.model,
            "prompt_generated": True,
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
        session_id = find_first_value(parse_json_body(query_result.body), {"session_id", "sessionId"})
        if session_id:
            session_link = client.build_session_link(session_id)
        else:
            errors.append("Eureka query response did not include session_id")
    else:
        errors.append(_curl_error_message("Eureka query", query_result.return_code, query_result.status_code, query_result.stderr))

    if session_id:
        share_result = client.create_share(session_id)
        if share_result.success:
            share_id = find_first_value(parse_json_body(share_result.body), {"share_id", "shareId"})
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
                )
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
        "errors": errors,
        "debug": {
            **(state.get("debug") or {}),
            "curl_task": "called_eureka_query_and_share",
        },
    }


def finalize_result(state: TopicWorkflowState) -> dict[str, Any]:
    rows = [
        {
            "输入": state.get("topic", ""),
            "generate prompt 后的 prompt": state.get("generated_prompt", ""),
            "session 会话链接": state.get("session_link", ""),
            "最终分享链接": state.get("share_link", ""),
        }
    ]

    return {
        "result_table_rows": rows,
        "result_table_markdown": _build_markdown_table(rows),
        "debug": {
            **(state.get("debug") or {}),
            "finished": True,
        }
    }


def _curl_error_message(label: str, return_code: int, status_code: int, stderr: str) -> str:
    if return_code != 0:
        return f"{label} curl exited with code {return_code}: {stderr}"
    return f"{label} returned HTTP {status_code}"


def _build_markdown_table(rows: list[dict[str, str]]) -> str:
    headers = ["输入", "generate prompt 后的 prompt", "session 会话链接", "最终分享链接"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>").strip()
