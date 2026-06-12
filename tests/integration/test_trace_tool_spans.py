import json
import sqlite3

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.observability import TraceQuery, query_trace_events
from fleetent.observability import traces as traces_mod
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


@pytest.fixture
def trace_db(tmp_path, monkeypatch):
    db_path = tmp_path / "traces.db"
    apply_migrations(db_path)
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("fleetent.observability.traces._state_db", db)
    return db_path


def test_record_tool_call_persists_tool_call_event_shape(trace_db):
    traces_mod.record_tool_call(
        "run-1",
        "session-1",
        {
            "tool_name": "send_file",
            "tool_call_id": "tc-1",
            "args_summary": '{"path": "/tmp/x"}',
            "failed": False,
            "duration_ms": 12.5,
            "risk": "low",
        },
    )

    with sqlite3.connect(trace_db) as conn:
        row = conn.execute(
            "SELECT run_id, session_id, event_type, payload_json FROM traces"
        ).fetchone()

    assert row is not None
    assert row[0] == "run-1"
    assert row[1] == "session-1"
    assert row[2] == "tool_call"
    payload = json.loads(row[3])
    assert payload["tool_name"] == "send_file"
    assert payload["tool_call_id"] == "tc-1"
    assert payload["failed"] is False
    assert payload["duration_ms"] == 12.5
    assert payload["risk"] == "low"
    assert "args_summary" in payload


def test_record_tool_call_queryable_by_session(trace_db):
    traces_mod.record_tool_call(
        "run-1",
        "session-A",
        {
            "tool_name": "read_file",
            "tool_call_id": "tc-2",
            "args_summary": "{}",
            "failed": True,
            "duration_ms": 3.0,
            "risk": "low",
        },
    )

    events = list(query_trace_events(TraceQuery(session_id="session-A", event_type="tool_call")))

    assert len(events) == 1
    assert events[0].payload["failed"] is True
    assert events[0].session_id == "session-A"


def test_record_tool_call_write_failure_only_warns(trace_db, monkeypatch, caplog):
    def _boom(_event):
        raise RuntimeError("db down")

    monkeypatch.setattr(traces_mod, "record_trace_event", _boom)

    # MUST NOT raise — observability is a side channel.
    traces_mod.record_tool_call(
        "run-1",
        "session-1",
        {
            "tool_name": "send_file",
            "tool_call_id": "tc-3",
            "args_summary": "{}",
            "failed": False,
            "duration_ms": 1.0,
            "risk": "low",
        },
    )
