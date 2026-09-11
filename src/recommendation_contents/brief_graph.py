"""Stage-one-only runner, sharing its operation with the end-to-end graph."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from .brief_generation import generate_briefs
from .config import OpenAISettings, merged_env
from .llm import create_chat_model


class BriefInput(TypedDict, total=False):
    idea: str
    audience: dict[str, str]
    language: str
    count: int


class BriefOutput(TypedDict):
    result: dict[str, Any]


class BriefState(BriefInput, total=False):
    result: dict[str, Any]


def build_brief_graph(
    settings: OpenAISettings | None = None,
    llm: Any | None = None,
    env_file: str = ".env",
):
    from langgraph.graph import END, START, StateGraph

    model = llm

    def get_model():
        nonlocal model
        if model is None:
            model = create_chat_model(settings or OpenAISettings.from_env(merged_env(env_file)))
        return model

    def generate_topic(state):
        if state.get("audience") is not None:
            from .profile_topic_generation import generate_profile_topics

            return {"result": generate_profile_topics(state, get_model)}
        return {"result": generate_briefs(state, get_model)}

    workflow = StateGraph(BriefState, input_schema=BriefInput, output_schema=BriefOutput)
    workflow.add_node("generate_topic", generate_topic)
    workflow.add_edge(START, "generate_topic")
    workflow.add_edge("generate_topic", END)
    return workflow.compile()
