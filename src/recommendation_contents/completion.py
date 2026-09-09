"""Parse Eureka session event responses into completion status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMPLETED_STATUSES = {"complete", "completed", "done", "finished", "success", "succeeded"}
FAILED_STATUSES = {"error", "errored", "fail", "failed", "failure"}
RUNNING_STATUSES = {"created", "in_progress", "pending", "processing", "queued", "running", "started"}


@dataclass(frozen=True)
class CompletionStatus:
    status: str
    is_complete: bool
    error_message: str = ""
    status_path: str = ""
    status_value: Any = None
    error_path: str = ""


def parse_completion_status(data: Any) -> CompletionStatus:
    status_path, status_value = _top_level_status(data)
    event_items = list(_iter_event_dicts(data))
    if not status_path:
        status_path, status_value = _latest_status(event_items) or _latest_generic_status(data)
    status = _normalize_status(status_value)
    if status == "unknown" and _has_truthy_completion(data):
        status = "completed"
        status_path = status_path or "completion"

    error_path, error_message = _latest_error_message(event_items)
    if status != "failed":
        error_path = ""
        error_message = ""
    elif not error_message:
        error_message = "Eureka session failed"

    return CompletionStatus(
        status=status,
        is_complete=status == "completed",
        error_message=error_message,
        status_path=status_path,
        status_value=status_value,
        error_path=error_path,
    )


def _top_level_status(data: Any) -> tuple[str, Any]:
    if not isinstance(data, dict):
        return "", None
    for key in ("status", "state"):
        if key in data:
            return key, data[key]
    return "", None


def _iter_event_dicts(data: Any, path: str = ""):
    if isinstance(data, dict):
        if _looks_like_event(data):
            yield path or "root", data
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else key
            yield from _iter_event_dicts(value, child_path)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _iter_event_dicts(value, f"{path}[{index}]")


def _looks_like_event(value: dict[str, Any]) -> bool:
    return any(str(key).lower() in {"status", "state", "type"} for key in value)


def _latest_status(event_items: list[tuple[str, dict[str, Any]]]) -> tuple[str, Any] | None:
    latest_path = ""
    latest_value: Any = None
    for path, event in event_items:
        for key, value in event.items():
            if str(key).lower() in {"status", "state"}:
                latest_path = f"{path}.{key}" if path else str(key)
                latest_value = value
    return (latest_path, latest_value) if latest_path else None


def _latest_generic_status(data: Any, path: str = "") -> tuple[str, Any]:
    latest_path = ""
    latest_value: Any = None
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = str(key).lower()
            current_path = f"{path}.{key}" if path else str(key)
            if normalized_key in {
                "completion",
                "completed",
                "iscomplete",
                "is_complete",
                "status",
                "state",
            }:
                latest_path = current_path
                latest_value = value
            child_path, child_value = _latest_generic_status(value, current_path)
            if child_path:
                latest_path = child_path
                latest_value = child_value
    elif isinstance(data, list):
        for index, value in enumerate(data):
            child_path, child_value = _latest_generic_status(value, f"{path}[{index}]")
            if child_path:
                latest_path = child_path
                latest_value = child_value
    return latest_path, latest_value


def _normalize_status(value: Any) -> str:
    if isinstance(value, bool):
        return "completed" if value else "running"
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in COMPLETED_STATUSES:
            return "completed"
        if normalized in FAILED_STATUSES:
            return "failed"
        if normalized in RUNNING_STATUSES:
            return "running"
    if value is None:
        return "unknown"
    if isinstance(value, (dict, list)):
        return "completed" if bool(value) else "running"
    return "completed" if bool(value) else "running"


def _has_truthy_completion(data: Any) -> bool:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = str(key).lower()
            if normalized_key in {"completion", "completed", "iscomplete", "is_complete"}:
                return _normalize_status(value) == "completed"
            if _has_truthy_completion(value):
                return True
    elif isinstance(data, list):
        return any(_has_truthy_completion(value) for value in data)
    return False


def _latest_error_message(event_items: list[tuple[str, dict[str, Any]]]) -> tuple[str, str]:
    latest_path = ""
    latest_message = ""
    for path, event in event_items:
        event_type = str(event.get("type", "")).strip().lower()
        event_status = _normalize_status(event.get("status") or event.get("state"))
        if event_type == "error" or event_status == "failed":
            message_path, message = _message_from(event, path)
            if message:
                latest_path = message_path
                latest_message = message
    return latest_path, latest_message


def _message_from(data: Any, path: str = "") -> tuple[str, str]:
    if isinstance(data, dict):
        for key in ("message", "error_message", "errorMessage", "msg", "reason"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return f"{path}.{key}" if path else key, value.strip()
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else str(key)
            message_path, message = _message_from(value, child_path)
            if message:
                return message_path, message
    elif isinstance(data, list):
        for index, value in enumerate(data):
            message_path, message = _message_from(value, f"{path}[{index}]")
            if message:
                return message_path, message
    return "", ""
