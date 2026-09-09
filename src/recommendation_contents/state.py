"""Shared graph state types."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class TopicWorkflowState(TypedDict, total=False):
    topic: str
    request_context: dict[str, Any]
    prompt_generation_raw_response: str
    generated_prompt: str
    title: str
    categories: list[str]
    keywords: list[str]
    description: str
    role: str
    industry: str
    jtbd: list[str]
    date: str
    sub_industry: list[str]
    token_status: str
    token_reason: str
    token_source: str
    token_refresh_available: bool
    token_refresh_attempted: bool
    token_refresh_success: bool
    token_refresh_error: str
    eureka_auth_status: str
    curl_payload: dict[str, Any]
    curl_response: str
    curl_success: bool
    curl_skipped: bool
    eureka_query_payload: dict[str, Any]
    eureka_query_response: str
    eureka_query_status_code: int
    eureka_query_return_code: int
    eureka_share_payload: dict[str, Any]
    eureka_share_response: str
    eureka_share_status_code: int
    eureka_share_return_code: int
    session_id: str
    session_link: str
    share_id: str
    share_link: str
    completion_required: bool
    completion_checked: bool
    isCompleted: bool
    completion_status: str
    completion_value: Any
    completion_error: str
    completion_status_path: str
    completion_error_path: str
    completion_poll_count: int
    eureka_completion_response: str
    eureka_completion_status_code: int
    eureka_completion_return_code: int
    result_table_rows: list[dict[str, str]]
    result_table_markdown: str
    errors: list[str]
    debug: dict[str, Any]
