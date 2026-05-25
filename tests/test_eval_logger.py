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
    assert "reply" in entry


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


def test_log_run_writes_entry(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run(
        user_input="ping",
        reply="pong",
        messages=[{"role": "user", "content": "ping"}],
        elapsed_s=0.5,
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["input"] == "ping"
    assert entry["reply"] == "pong"
    assert entry["elapsed_s"] == 0.5
    assert entry["tokens"] is None
    assert "ts" in entry


def test_log_run_with_usage(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15
    el.log_run("hi", "hello", [], 0.1, usage=usage)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["tokens"] == {"prompt": 10, "completion": 5, "total": 15}


def test_serialize_model_dump():
    from mini_agent.eval_logger import _serialize

    class FakeMsg:
        def model_dump(self):
            return {"role": "assistant", "content": "reply"}

    assert _serialize(FakeMsg()) == {"role": "assistant", "content": "reply"}


def test_serialize_fallback_str():
    from mini_agent.eval_logger import _serialize

    class Unknown:
        def __str__(self):
            return "custom_repr"

    assert _serialize(Unknown()) == "custom_repr"


# --- model_used ---

def test_log_run_model_used_written_to_trace(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, model_used="claude-haiku-4-5")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["model_used"] == "claude-haiku-4-5"


def test_log_run_model_used_omitted_when_not_provided(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "model_used" not in entry


# --- user_id ---

def test_log_run_user_id_written(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, user_id="user-42")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["user_id"] == "user-42"


def test_log_run_user_id_omitted_when_not_provided(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "user_id" not in entry


# --- agent_name ---

def test_log_run_agent_name_written(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, agent_name="support-bot")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["agent_name"] == "support-bot"


def test_log_run_agent_name_omitted_when_not_provided(tmp_path, monkeypatch):
    import mini_agent.eval_logger as el

    monkeypatch.setattr(el, "_LOG_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "agent_name" not in entry
