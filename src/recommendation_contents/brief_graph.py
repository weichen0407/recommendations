"""Standalone stage-one graph: idea -> classified, validated content briefs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from typing_extensions import TypedDict

from .brief_prompts import build_brief_messages
from .brief_schema import (
    LANGUAGES,
    MAX_BRIEFS,
    SCHEMA_VERSION,
    load_brief_catalog,
    parse_brief_response,
    validate_briefs,
)
from .config import OpenAISettings, merged_env
from .llm import create_chat_model


class BriefInput(TypedDict, total=False):
    idea: str
    language: str
    count: int


class BriefOutput(TypedDict):
    result: dict[str, Any]


class BriefState(BriefInput, total=False):
    request: dict[str, Any]
    raw_response: str
    candidate: dict[str, Any]
    errors: list[str]
    fatal: bool
    attempts: int
    result: dict[str, Any]


def normalize_idea(state: BriefState) -> dict[str, Any]:
    idea, language, count = state.get("idea"), state.get("language", "zh-CN"), state.get("count", 1)
    errors = []
    if not isinstance(idea, str) or not idea.strip() or len(idea) > 8000:
        errors.append("idea must be a non-blank string of at most 8000 characters")
    if language not in LANGUAGES:
        errors.append("language must be zh-CN or en")
    if type(count) is not int or not 1 <= count <= MAX_BRIEFS:
        errors.append(f"count must be an integer between 1 and {MAX_BRIEFS}")
    return {
        "request": {
            "idea": idea.strip() if isinstance(idea, str) else None,
            "language": language,
            "count": count,
        },
        "errors": errors,
        "fatal": bool(errors),
        "attempts": 0,
        "candidate": {},
        "raw_response": "",
        "result": {},
    }


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
            and block.get("type") in {"text", "output_text"}
        )
    raise ValueError("model returned no text content")


def build_graph():
    """LangGraph server factory; no Eureka configuration or credentials are loaded."""
    return build_brief_graph()


def build_brief_graph(
    settings: OpenAISettings | None = None,
    llm: Any | None = None,
    env_file: str = ".env",
):
    from langgraph.graph import END, START, StateGraph

    catalog = load_brief_catalog()
    model = llm

    def generate(state: BriefState) -> dict[str, Any]:
        nonlocal model
        attempts = state["attempts"] + 1
        try:
            if model is None:
                model = create_chat_model(settings or OpenAISettings.from_env(merged_env(env_file)))
            messages = build_brief_messages(
                state["request"],
                catalog,
                previous_response=state["raw_response"] if state["attempts"] else None,
                errors=state["errors"],
            )
            raw = _response_text(model.invoke(messages))
            if len(raw) > 200000:
                raise ValueError("model response exceeds size limit")
            return {"raw_response": raw, "attempts": attempts, "fatal": False}
        except Exception as exc:  # noqa: BLE001 - isolate the model-provider boundary
            # Provider exception messages may contain endpoint or authentication details.
            return {
                "attempts": attempts,
                "fatal": True,
                "candidate": {},
                "errors": [
                    f"LLM request failed ({type(exc).__name__}); check model configuration."
                ],
            }

    def validate(state: BriefState) -> dict[str, Any]:
        try:
            candidate = parse_brief_response(state["raw_response"])
        except (ValueError, RecursionError):
            return {"candidate": {}, "errors": ["Response must be a JSON object with unique keys."]}
        errors = validate_briefs(candidate, catalog, state["request"]["count"])
        return {"candidate": candidate if not errors else {}, "errors": errors}

    def finalize(state: BriefState) -> dict[str, Any]:
        generation_id = str(uuid4())
        valid = not state["errors"] and not state["fatal"] and bool(state["candidate"])
        briefs = (
            [{"brief_id": str(uuid4()), **brief} for brief in state["candidate"].get("briefs", [])]
            if valid
            else []
        )
        return {
            "result": {
                "status": "succeeded" if valid else "failed",
                "schema_version": SCHEMA_VERSION,
                "taxonomy_version": catalog["taxonomy_version"],
                "generation_id": generation_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "input": state["request"],
                "attempts": state["attempts"],
                "briefs": briefs,
                "errors": state["errors"],
            }
        }

    workflow = StateGraph(BriefState, input_schema=BriefInput, output_schema=BriefOutput)
    workflow.add_node("normalize_idea", normalize_idea)
    workflow.add_node("generate_content_brief", generate)
    workflow.add_node("validate_content_brief", validate)
    workflow.add_node("repair_content_brief", generate)
    workflow.add_node("finalize_content_brief", finalize)
    workflow.add_edge(START, "normalize_idea")
    workflow.add_conditional_edges(
        "normalize_idea",
        lambda state: "stop" if state["fatal"] else "generate",
        {"stop": "finalize_content_brief", "generate": "generate_content_brief"},
    )
    for node in ("generate_content_brief", "repair_content_brief"):
        workflow.add_conditional_edges(
            node,
            lambda state: "stop" if state["fatal"] else "validate",
            {"stop": "finalize_content_brief", "validate": "validate_content_brief"},
        )
    workflow.add_conditional_edges(
        "validate_content_brief",
        lambda state: "repair" if state["errors"] and state["attempts"] < 2 else "finish",
        {"repair": "repair_content_brief", "finish": "finalize_content_brief"},
    )
    workflow.add_edge("finalize_content_brief", END)
    return workflow.compile()
