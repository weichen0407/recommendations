"""LangGraph assembly."""

from __future__ import annotations

from typing import Any

from .config import AppSettings
from .nodes import (
    RuntimeDependencies,
    call_curl_task,
    finalize_result,
    generate_prompt,
    normalize_topic,
)
from .services.eureka_curl import EurekaCurlClient
from .state import TopicWorkflowState


def build_graph():
    return build_graph_with_dependencies()


def build_graph_with_dependencies(
    settings: AppSettings | None = None,
    llm: Any | None = None,
    eureka_client: EurekaCurlClient | None = None,
):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("langgraph is not installed. Run `python -m pip install -e .` first.") from exc

    runtime = RuntimeDependencies(
        settings=settings or AppSettings.from_env_file(),
        llm=llm,
        eureka_client=eureka_client,
    )

    workflow = StateGraph(TopicWorkflowState)
    workflow.add_node("normalize_topic", normalize_topic)
    workflow.add_node("generate_prompt", lambda state: generate_prompt(state, runtime))
    workflow.add_node("call_curl_task", lambda state: call_curl_task(state, runtime))
    workflow.add_node("finalize_result", finalize_result)

    workflow.add_edge(START, "normalize_topic")
    workflow.add_edge("normalize_topic", "generate_prompt")
    workflow.add_edge("generate_prompt", "call_curl_task")
    workflow.add_edge("call_curl_task", "finalize_result")
    workflow.add_edge("finalize_result", END)

    return workflow.compile()
