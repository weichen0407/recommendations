"""Shared graph state types."""

from __future__ import annotations

from typing import Any, TypedDict


class TopicWorkflowState(TypedDict, total=False):
    topic: str
    request_context: dict[str, Any]
    generated_prompt: str
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
    result_table_rows: list[dict[str, str]]
    result_table_markdown: str
    errors: list[str]
    debug: dict[str, Any]
