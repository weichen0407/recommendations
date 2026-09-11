"""End-to-end graph with two generation nodes and one Eureka execution node."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict

from .brief_generation import generate_briefs
from .config import AppSettings
from .nodes import RuntimeDependencies
from .records import build_markdown_table
from .summary_generation import (
    GenerationError,
    generate_task_specs,
)
from .workflow_execution import DEFAULT_RUNS_DIR, execute_tasks, read_run, run_path
from .workflow_stages import validate_generation_result, validate_task_specs


class WorkflowInput(TypedDict, total=False):
    topic: str
    idea: str
    language: str
    count: int
    format: str
    request_context: dict[str, Any]
    resume_run_id: str
    stage_result: dict[str, Any] | None


class WorkflowOutput(TypedDict, total=False):
    topic: str
    format: str
    generation_result: dict[str, Any]
    task_specs: list[dict[str, Any]]
    results: list[dict[str, Any]]
    status: str
    run_record_path: str
    result_table_rows: list[dict[str, str]]
    result_table_markdown: str
    generated_prompt: str
    session_id: str
    session_link: str
    share_link: str
    errors: list[str]


class WorkflowState(WorkflowInput, WorkflowOutput, total=False):
    summary_attempts: int


def build_graph():
    return build_graph_with_dependencies()


def build_graph_with_dependencies(
    settings: AppSettings | None = None,
    llm: Any | None = None,
    eureka_client: Any | None = None,
    eureka_token_manager: Any | None = None,
    runs_dir: Path | None = DEFAULT_RUNS_DIR,
    *,
    checkpointer=None,
    sleep=time.sleep,
    monotonic=time.monotonic,
):
    from langgraph.graph import END, START, StateGraph

    runtime = RuntimeDependencies(settings=settings or AppSettings.from_env_file(), llm=llm)

    def generate_topic(state):
        resume_id = state.get("resume_run_id")
        stage_result = state.get("stage_result")
        context = state.get("request_context") or {}
        if not isinstance(context, dict):
            raise GenerationError("generate_topic", ["request_context must be an object."])
        output_format = state.get("format", context.get("format", "html"))
        if output_format not in ("html", "report"):
            raise GenerationError("generate_topic", ["format must be html or report."])
        if resume_id and stage_result is not None:
            raise GenerationError("generate_topic", ["Use either resume_run_id or stage_result."])
        if resume_id:
            if runs_dir is None:
                raise GenerationError("generate_topic", ["Resume requires a runs directory."])
            try:
                saved = read_run(run_path(Path(runs_dir), resume_id))
            except (OSError, ValueError, TypeError, AttributeError):
                raise GenerationError("generate_topic", ["Cannot read the saved run."]) from None
            generation, specs = saved.get("generation_result"), saved.get("task_specs")
            validate_generation_result(generation, "generate_topic")
            if generation["generation_id"] != resume_id:
                raise GenerationError("generate_topic", ["Saved generation ID is invalid."])
            if isinstance(specs, list) and specs and isinstance(specs[0], dict):
                output_format = specs[0].get("format")
            validate_task_specs(generation, specs, output_format, "generate_topic")
        elif stage_result is not None:
            if not isinstance(stage_result, dict):
                raise GenerationError("generate_topic", ["stage_result must be an object."])
            # Accept both the stage-one CLI envelope and an end-to-end stage snapshot.
            generation = stage_result.get("generation_result", stage_result)
            validate_generation_result(generation, "generate_topic")
            specs = stage_result.get("task_specs", [])
            if not isinstance(specs, list):
                raise GenerationError("generate_topic", ["task_specs must be an array."])
            output_format = state.get("format", stage_result.get("format", output_format))
            if output_format not in ("html", "report"):
                raise GenerationError("generate_topic", ["format must be html or report."])
            if specs:
                validate_task_specs(generation, specs, output_format, "generate_topic")
        else:
            generation = generate_briefs(
                {
                    "idea": state.get("idea", state.get("topic")),
                    "language": state.get("language", context.get("language", "zh-CN")),
                    "count": state.get("count", 1),
                },
                runtime.get_llm,
            )
            if generation["status"] != "succeeded":
                raise GenerationError("generate_topic", generation["errors"])
            specs = []
        return {
            "topic": generation["input"]["idea"],
            "generation_result": generation,
            "task_specs": specs,
            "format": output_format,
            "resume_run_id": "",
            "stage_result": None,
            "results": [],
            "errors": [],
            "status": "topic_generated",
            "summary_attempts": 0,
            "generated_prompt": "",
            "session_id": "",
            "session_link": "",
            "share_link": "",
            "result_table_rows": [],
            "result_table_markdown": "",
            "run_record_path": "",
        }

    def generate_summary(state):
        validate_generation_result(state["generation_result"], "generate_summary")
        if state["format"] not in ("html", "report"):
            raise GenerationError("generate_summary", ["format must be html or report."])
        specs = state["task_specs"]
        attempts = 0
        if specs != []:
            validate_task_specs(
                state["generation_result"], specs, state["format"], "generate_summary"
            )
        else:
            specs, attempts = generate_task_specs(
                state["generation_result"],
                state["format"],
                runtime.get_llm,
            )
        return {
            "task_specs": specs,
            "summary_attempts": attempts,
            "generated_prompt": specs[0]["generated_prompt"],
            "status": "summary_generated",
        }

    def call_curl_task(state):
        validate_generation_result(state["generation_result"], "call_curl_task")
        validate_task_specs(
            state["generation_result"], state["task_specs"], state["format"], "call_curl_task"
        )
        # Auth/client objects belong to this execution, not to a shared graph state.
        execution_runtime = RuntimeDependencies(
            settings=runtime.settings,
            eureka_client=eureka_client,
            eureka_token_manager=eureka_token_manager,
        )
        generation = state["generation_result"]
        path = (
            run_path(Path(runs_dir), generation["generation_id"]) if runs_dir is not None else None
        )
        results, status = execute_tasks(
            generation,
            state["task_specs"],
            execution_runtime,
            path,
            sleep=sleep,
            monotonic=monotonic,
        )
        rows = [
            _result_row(generation, spec, result)
            for spec, result in zip(state["task_specs"], results)
        ]
        first = results[0]
        return {
            "results": results,
            "status": status,
            "run_record_path": str(path.resolve()) if path else "",
            "result_table_rows": rows,
            "result_table_markdown": build_markdown_table(rows),
            "session_id": first["session_id"],
            "session_link": first["session_url"],
            "share_link": first["share_url"],
            "errors": [e for r in results for e in r["errors"]],
        }

    workflow = StateGraph(WorkflowState, input_schema=WorkflowInput, output_schema=WorkflowOutput)
    workflow.add_node("generate_topic", generate_topic)
    workflow.add_node("generate_summary", generate_summary)
    workflow.add_node("call_curl_task", call_curl_task)
    workflow.add_edge(START, "generate_topic")
    workflow.add_edge("generate_topic", "generate_summary")
    workflow.add_edge("generate_summary", "call_curl_task")
    workflow.add_edge("call_curl_task", END)
    return workflow.compile(checkpointer=checkpointer)


def _result_row(generation, spec, result):
    brief = spec["brief"]
    audience, tags = brief["audience"], brief["tags"]
    encode = lambda value: json.dumps(value, ensure_ascii=False)
    return {
        "input": generation["input"]["idea"],
        "generated_prompt": spec["generated_prompt"],
        "session_url": result["session_url"],
        "share_url": result["share_url"],
        "format": spec["format"],
        "isCompleted": str(result["isCompleted"]).lower(),
        "completionStatus": result["completion_status"],
        "completionError": "; ".join(result["errors"]),
        "title": brief["title"],
        "categories": encode([spec["content_category"]]),
        "keywords": encode(brief["keywords"]),
        "description": brief["description"],
        "role": audience["role"],
        "industry": audience["industry"],
        "jtbd": encode([audience["jtbd"]]),
        "date": generation["generated_at"][:10],
        "sub_industry": encode([tags["industry_segment"]] if tags["industry_segment"] else []),
        "brief_id": brief["brief_id"],
        "generation_id": generation["generation_id"],
        "taxonomy_version": generation["taxonomy_version"],
        "tags": encode(tags),
        "classification": encode(brief["classification"]),
        "assumptions": encode(brief["assumptions"]),
        "status": result["status"],
    }
