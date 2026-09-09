from recommendation_contents.completion import parse_completion_status


def test_parse_completion_status_uses_latest_event_status():
    status = parse_completion_status(
        {
            "data": {
                "events": [
                    {"id": 1, "status": "running"},
                    {"id": 2, "status": "completed"},
                ]
            }
        }
    )

    assert status.status == "completed"
    assert status.is_complete is True
    assert status.error_message == ""
    assert status.status_path == "data.events[1].status"


def test_parse_completion_status_prefers_top_level_session_status():
    status = parse_completion_status(
        {
            "cursor": "archive:1788923287434-0",
            "events": [
                {"type": "answer_chunk", "session_id": "sess_11016e83cc9e4b66"},
                {"type": "tool_call", "status": "running"},
            ],
            "has_more": True,
            "source": "history",
            "status": "completed",
            "terminal": True,
        }
    )

    assert status.status == "completed"
    assert status.is_complete is True
    assert status.status_path == "status"


def test_parse_completion_status_keeps_running_incomplete():
    status = parse_completion_status({"events": [{"status": "running"}]})

    assert status.status == "running"
    assert status.is_complete is False


def test_parse_completion_status_extracts_error_event_message():
    status = parse_completion_status(
        {
            "events": [
                {"status": "running"},
                {"status": "failed"},
                {"type": "error", "message": "artifact generation failed"},
            ]
        }
    )

    assert status.status == "failed"
    assert status.is_complete is False
    assert status.error_message == "artifact generation failed"
    assert status.error_path == "events[2].message"


def test_parse_completion_status_supports_completion_field():
    status = parse_completion_status({"data": {"completion": {"content": "done"}}})

    assert status.status == "completed"
    assert status.is_complete is True
