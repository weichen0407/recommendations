"""Eureka execution and resumable local records behind one graph node."""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .completion import CompletionStatus, parse_completion_status
from .nodes import check_user_token, refresh_user_token, route_after_token_check
from .services.eureka_curl import find_first_value, parse_json_body

DEFAULT_RUNS_DIR = Path("outputs/topic_workflow_runs")


def run_path(directory: Path, run_id: str) -> Path:
    return directory / f"{UUID(run_id)}.json"


def read_run(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("workflow_version") != "2.0.0":
        raise ValueError("Unsupported workflow record version")
    return data


def write_run(path: Path | None, data: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _run_lock(path: Path | None):
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("This run is already executing; wait before resuming it.") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read_completion(client, session_id: str) -> dict[str, Any]:
    cursor, seen, events = "", set(), []
    for _ in range(20):
        response = client.get_completion_status(session_id, cursor=cursor)
        if not response.success:
            raise ValueError(f"Completion query failed (HTTP {response.status_code}).")
        page = parse_json_body(response.body)
        if not isinstance(page, dict):
            raise TypeError("Completion response must be a JSON object.")
        page_events = page.get("events", [])
        if isinstance(page_events, list):
            events.extend(page_events)
        more = page.get("has_more", page.get("hasMore", False))
        if more not in (True, "true"):
            return {**page, "events": events} if events else page
        cursor = next(
            (
                page.get(k)
                for k in (
                    "stream_cursor",
                    "streamCursor",
                    "cursor",
                    "next_cursor",
                    "nextCursor",
                )
                if isinstance(page.get(k), str) and page[k]
            ),
            "",
        )
        if not cursor or cursor in seen:
            raise ValueError("Completion pagination has a missing or repeated cursor.")
        seen.add(cursor)
    raise ValueError("Completion pagination exceeded 20 pages.")


def _session_completion(payload: dict[str, Any]) -> CompletionStatus:
    # A completed tool event or an HTTP-envelope success flag is not a completed session.
    status = payload.get("status", payload.get("state"))
    if isinstance(status, str):
        return parse_completion_status({**payload, "status": status})
    for container in (payload, payload.get("data")):
        if isinstance(container, dict) and "completion" in container:
            return parse_completion_status({"completion": container["completion"]})
    return CompletionStatus(status="unknown", is_complete=False)


def execute_tasks(
    generation: dict[str, Any],
    specs: list[dict[str, Any]],
    runtime,
    path: Path | None,
    *,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> tuple[list[dict[str, Any]], str]:
    with _run_lock(path):
        previous = read_run(path) if path is not None and path.exists() else None
        if previous and previous["task_specs"] != specs:
            raise ValueError("Saved execution prompts do not match this run; use a new run ID.")
        by_id = {r["brief_id"]: r for r in previous["results"]} if previous else {}
        results = [
            by_id.get(
                spec["brief_id"],
                {
                    "brief_id": spec["brief_id"],
                    "status": "prepared",
                    "session_id": "",
                    "session_url": "",
                    "share_id": "",
                    "share_url": "",
                    "share_status": "pending",
                    "isCompleted": False,
                    "completion_status": "",
                    "errors": [],
                },
            )
            for spec in specs
        ]

        def save():
            write_run(
                path,
                {
                    "workflow_version": "2.0.0",
                    "generation_result": generation,
                    "task_specs": specs,
                    "results": results,
                },
            )

        save()
        auth = check_user_token({}, runtime)
        if route_after_token_check(auth) == "refresh_user_token":
            auth.update(refresh_user_token(auth, runtime))
            auth.update(check_user_token(auth, runtime))
        client = runtime.get_eureka_client()
        for spec, result in zip(specs, results):
            if result["status"] in {"completed", "failed", "submission_unknown", "submitting"}:
                if result["status"] == "submitting":
                    result.update(
                        status="submission_unknown",
                        errors=[
                            "Submission was interrupted; verify the remote task before creating another."
                        ],
                    )
                continue
            if not client.has_authorization_header():
                result.update(
                    status="needs_auth", errors=["Eureka authorization is missing or expired."]
                )
                continue
            result["errors"] = []
            if not result["session_id"]:
                result["status"] = "submitting"
                save()  # Persist intent BEFORE the side effect; never blindly retry ambiguous submits.
                try:
                    response = client.create_conversation(spec["generated_prompt"])
                except Exception as exc:  # noqa: BLE001 - external client boundary
                    result.update(
                        status="submission_unknown",
                        errors=[f"Submission interrupted ({type(exc).__name__})."],
                    )
                    save()
                    continue
                payload = parse_json_body(response.body)
                rejected = isinstance(payload, dict) and (
                    payload.get("status") is False or payload.get("success") is False
                )
                if response.status_code == 401:
                    result.update(
                        status="needs_auth", errors=["Eureka rejected authorization (401)."]
                    )
                elif rejected or 400 <= response.status_code < 500:
                    result.update(status="failed", errors=["Eureka rejected the task submission."])
                elif not response.success:
                    result.update(
                        status="submission_unknown",
                        errors=["Submission outcome is uncertain; do not auto-resubmit."],
                    )
                else:
                    session_id = find_first_value(payload, {"session_id", "sessionId"})
                    if session_id:
                        result.update(
                            status="submitted",
                            session_id=session_id,
                            session_url=client.build_session_link(session_id),
                        )
                    else:
                        result.update(
                            status="submission_unknown",
                            errors=["Submission returned no session ID."],
                        )
                save()
                if not result["session_id"]:
                    continue
            if not result["share_id"] and result["share_status"] == "pending":
                result["share_status"] = "submitting"
                save()
                try:
                    response = client.create_share(result["session_id"])
                    share_payload = parse_json_body(response.body)
                    share_id = (
                        find_first_value(share_payload, {"share_id", "shareId"})
                        if response.success
                        else ""
                    )
                    if share_id:
                        result.update(
                            share_id=share_id,
                            share_url=client.build_share_link(share_id),
                            share_status="created",
                        )
                    else:
                        result["share_status"] = "unavailable"
                except Exception:  # noqa: BLE001 - a share failure must not discard the session ID
                    result["share_status"] = "unavailable"
                save()
            if not client.has_completion_endpoint():
                result.update(status="submitted", errors=["No completion endpoint is configured."])
                save()
                continue
            deadline = monotonic() + max(0, runtime.settings.eureka.completion_timeout_seconds)
            while True:
                try:
                    payload = _read_completion(client, result["session_id"])
                    completion = _session_completion(payload)
                except Exception as exc:  # noqa: BLE001 - keep submitted sessions resumable
                    result.update(
                        status="pending",
                        errors=[
                            f"Completion query failed ({type(exc).__name__}); resume this run."
                        ],
                    )
                    break
                result.update(
                    completion_response=payload,
                    completion_status=completion.status,
                    isCompleted=completion.is_complete,
                    completion_poll_count=result.get("completion_poll_count", 0) + 1,
                )
                if completion.is_complete:
                    result["status"] = "completed"
                    break
                if completion.status == "failed":
                    result.update(status="failed", errors=[completion.error_message])
                    break
                if monotonic() >= deadline:
                    result.update(
                        status="pending",
                        errors=[
                            "Wait limit reached; resume this run to keep checking the same session."
                        ],
                    )
                    break
                result["status"] = "running"
                save()
                sleep(
                    min(
                        60,
                        max(0.1, runtime.settings.eureka.completion_poll_interval_seconds),
                        max(0, deadline - monotonic()),
                    )
                )
            save()
        save()
        statuses = {r["status"] for r in results}
        overall = (
            "succeeded"
            if statuses == {"completed"}
            else (
                "pending"
                if statuses <= {"completed", "pending", "running", "submitted"}
                else "failed"
            )
        )
        return results, overall
