import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

import pytest

from fleetent.observability import TraceEvent, TraceQuery, query_trace_events, record_trace_event
from tests.test_migrations import apply_migrations


def test_trace_event_public_api_can_be_constructed():
    event = TraceEvent(
        run_id="run-1",
        event_type="agent_run_completed",
        payload={"reply": "done"},
    )
    query = TraceQuery(run_id="run-1")

    assert event.run_id == "run-1"
    assert event.event_type == "agent_run_completed"
    assert event.payload == {"reply": "done"}
    assert event.tenant_id == "default"
    assert query.run_id == "run-1"
    assert callable(record_trace_event)
    assert callable(query_trace_events)


def test_legacy_eval_logger_and_trace_log_names_are_not_public():
    sys.modules.pop("fleetent.eval_logger", None)

    with pytest.raises(ModuleNotFoundError):
        __import__("fleetent.eval_logger")

    import fleetent.observability as observability

    for name in ("log_run", "log", "TRACE_PATH"):
        assert not hasattr(observability, name)


@pytest.fixture
def trace_db(tmp_path, monkeypatch):
    db_path = tmp_path / "traces.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_record_trace_event_persists_payload_and_generates_defaults(trace_db):
    record_trace_event(
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"reply": "done"},
            user_id="user-1",
        )
    )

    with sqlite3.connect(trace_db) as conn:
        row = conn.execute(
            "SELECT id, run_id, event_type, ts, payload_json, user_id, tenant_id FROM traces"
        ).fetchone()

    assert row is not None
    assert row[0]
    assert row[1] == "run-1"
    assert row[2] == "agent_run_completed"
    assert datetime.fromisoformat(row[3]) <= datetime.now(UTC)
    assert json.loads(row[4]) == {"reply": "done"}
    assert row[5] == "user-1"
    assert row[6] == "default"


def test_query_trace_events_filters_by_run_user_agent_tenant_event_time_and_limit(trace_db):
    base_ts = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    events = [
        TraceEvent(
            id="event-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"idx": 1},
            ts=base_ts,
            user_id="user-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
        ),
        TraceEvent(
            id="event-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"idx": 2},
            ts=base_ts + timedelta(minutes=1),
            user_id="user-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
        ),
        TraceEvent(
            id="event-3",
            run_id="run-3",
            event_type="tool_call_completed",
            payload={"idx": 3},
            ts=base_ts + timedelta(minutes=2),
            user_id="user-2",
            agent_id="agent-2",
            tenant_id="tenant-2",
        ),
    ]
    for event in events:
        record_trace_event(event)

    assert [event.id for event in query_trace_events(TraceQuery(run_id="run-1"))] == ["event-1"]
    assert [event.id for event in query_trace_events(TraceQuery(user_id="user-1"))] == [
        "event-1",
        "event-2",
    ]
    assert [
        event.id
        for event in query_trace_events(
            TraceQuery(
                agent_id="agent-1",
                tenant_id="tenant-1",
                event_type="agent_run_completed",
                start_ts=base_ts + timedelta(seconds=30),
                end_ts=base_ts + timedelta(minutes=2),
                limit=1,
            )
        )
    ] == ["event-2"]


def test_record_trace_event_redacts_truncates_and_serializes_fallback(trace_db):
    record_trace_event(
        TraceEvent(
            run_id="run-safe",
            event_type="tool_call_completed",
            payload={
                "authorization": "Authorization: Bearer sk-sensitive",
                "password": "plain-password",
                "email": "alice@example.com",
                "phone": "13800138000",
                "large": "x" * 5000,
                "object": object(),
            },
        )
    )

    with sqlite3.connect(trace_db) as conn:
        raw_payload = conn.execute("SELECT payload_json FROM traces").fetchone()[0]
    payload = json.loads(raw_payload)

    assert "sk-sensitive" not in raw_payload
    assert "plain-password" not in raw_payload
    assert "alice@example.com" not in raw_payload
    assert "13800138000" not in raw_payload
    assert payload["authorization"] == "[REDACTED:token]"
    assert payload["password"] == "[REDACTED:token]"
    assert payload["email"] == "[REDACTED:email]"
    assert payload["phone"] == "[REDACTED:phone]"
    assert payload["large"]["truncated"] is True
    assert len(payload["large"]["value"]) < 5000
    assert isinstance(payload["object"], str)
    assert payload["serialization_fallback"] is True
