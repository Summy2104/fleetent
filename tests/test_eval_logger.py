"""Tests for eval_logger IM metadata fields."""

import json


def test_trace_with_im_metadata(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-1",
        messages=[{"role": "user", "content": "hi"}],
        response="hello",
        platform="slack",
        session_id="user:U123",
        channel_id="C999",
        thread_id="T456",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["platform"] == "slack"
    assert entry["session_id"] == "user:U123"
    assert entry["channel_id"] == "C999"
    assert entry["thread_id"] == "T456"


def test_trace_without_im_metadata_no_null_pollution(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-1",
        messages=[{"role": "user", "content": "hi"}],
        response="hello",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    # IM fields should not appear when not provided
    assert "platform" not in entry
    assert "session_id" not in entry
    assert "channel_id" not in entry
    assert "thread_id" not in entry
    assert "message_id" not in entry
    # Core fields must exist
    assert "user_id" in entry
    assert "response" in entry


def test_trace_with_message_id(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-2",
        messages=[{"role": "user", "content": "test"}],
        response="ok",
        platform="telegram",
        message_id="MSG-789",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["platform"] == "telegram"
    assert entry["message_id"] == "MSG-789"
    assert "session_id" not in entry
    assert "channel_id" not in entry
    assert "thread_id" not in entry
