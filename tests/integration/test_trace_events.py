import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from fleetent.observability import (
    InjectedContextTrace,
    TraceEvent,
    TraceQuery,
    query_trace_events,
    record_injected_context,
    record_trace_event,
)
from tests.integration.test_migrations import apply_migrations


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


def test_injected_context_trace_public_api_can_be_constructed():
    source = InjectedContextTrace(
        source_id="memory-1",
        source_type="memory",
        score=0.87,
        token_estimate=42,
        metadata={"memory_type": "preference"},
    )

    assert source.source_id == "memory-1"
    assert source.source_type == "memory"
    assert source.score == 0.87
    assert source.token_estimate == 42
    assert source.metadata == {"memory_type": "preference"}
    assert callable(record_injected_context)


# NOTE (next<-main integration): main consolidated logging onto observability and
# asserted fleetent.eval_logger was gone. The merged codebase still ships
# zhangyang's flat eval_logger (agent_loop / tools / context_mgr import it), so
# that "legacy name removed" assertion no longer holds and is dropped here.
# Follow-up: converge eval_logger onto observability/traces, then restore a guard.


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


def test_record_injected_context_persists_injected_context_event(trace_db):
    record_injected_context(
        "run-ctx",
        [
            InjectedContextTrace(
                source_id="memory-1",
                source_type="memory",
                score=0.91,
                token_estimate=0,
                metadata={"memory_type": "preference"},
            )
        ],
    )

    events = list(query_trace_events(TraceQuery(run_id="run-ctx", event_type="injected_context")))

    assert len(events) == 1
    event = events[0]
    assert event.run_id == "run-ctx"
    assert event.event_type == "injected_context"
    assert event.payload == {
        "sources": [
            {
                "source_id": "memory-1",
                "source_type": "memory",
                "score": 0.91,
                "token_estimate": 0,
                "metadata": {"memory_type": "preference"},
            }
        ]
    }


def test_record_injected_context_persists_summary_without_raw_content_fields(trace_db):
    record_injected_context(
        "run-safe",
        [
            InjectedContextTrace(
                source_id="knowledge-1",
                source_type="knowledge",
                score=0.74,
                token_estimate=31,
                metadata={
                    "kb_id": "kb-1",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "content": "full knowledge content",
                    "text": "raw text",
                    "transcript": "full conversation",
                },
            )
        ],
    )

    with sqlite3.connect(trace_db) as conn:
        raw_payload = conn.execute("SELECT payload_json FROM traces").fetchone()[0]

    assert "full knowledge content" not in raw_payload
    assert "raw text" not in raw_payload
    assert "full conversation" not in raw_payload
    payload = json.loads(raw_payload)
    source = payload["sources"][0]
    assert source == {
        "source_id": "knowledge-1",
        "source_type": "knowledge",
        "score": 0.74,
        "token_estimate": 31,
        "metadata": {
            "kb_id": "kb-1",
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
        },
    }


def test_record_injected_context_skips_empty_sources(monkeypatch):
    from fleetent.observability import traces

    calls: list[TraceEvent] = []
    monkeypatch.setattr(traces, "record_trace_event", calls.append)

    record_injected_context("run-empty", [])

    assert calls == []


def test_trace_database_url_fallback_uses_default_fleetent_database(monkeypatch):
    from fleetent import paths
    from fleetent.observability import traces

    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert traces._database_url() == f"sqlite:///{paths.data_dir() / 'fleetent.db'}"


def test_query_trace_events_can_filter_injected_context_events(trace_db):
    record_trace_event(
        TraceEvent(
            run_id="run-complete",
            event_type="agent_run_completed",
            payload={"reply": "done"},
        )
    )
    record_injected_context(
        "run-context",
        [
            InjectedContextTrace(
                source_id="memory-1",
                source_type="memory",
                score=1.0,
                token_estimate=9,
                metadata={"memory_type": "fact"},
            )
        ],
    )

    events = list(query_trace_events(TraceQuery(event_type="injected_context")))

    assert [event.run_id for event in events] == ["run-context"]
    assert events[0].payload["sources"][0]["source_id"] == "memory-1"


def test_record_injected_context_redacts_sensitive_metadata(trace_db):
    record_injected_context(
        "run-sensitive",
        [
            InjectedContextTrace(
                source_id="memory-sensitive",
                source_type="memory",
                score=1.0,
                token_estimate=12,
                metadata={
                    "token": "sk-sensitive",
                    "password": "plain-password",
                    "secret": "ma-" + "a" * 64,
                    "owner_email": "alice@example.com",
                    "owner_phone": "13800138000",
                },
            )
        ],
    )

    event = next(query_trace_events(TraceQuery(event_type="injected_context")))
    metadata = event.payload["sources"][0]["metadata"]
    raw_payload = json.dumps(event.payload)

    assert "sk-sensitive" not in raw_payload
    assert "plain-password" not in raw_payload
    assert "alice@example.com" not in raw_payload
    assert "13800138000" not in raw_payload
    assert metadata == {
        "token": "[REDACTED:token]",
        "password": "[REDACTED:token]",
        "secret": "[REDACTED:token]",
        "owner_email": "[REDACTED:email]",
        "owner_phone": "[REDACTED:phone]",
    }


def test_query_trace_events_filters_by_run_user_agent_tenant_event_time_and_limit(trace_db):
    base_ts = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    events = [
        TraceEvent(
            id="event-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"idx": 1},
            ts=base_ts,
            session_id="session-1",
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
            session_id="session-2",
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
            session_id="session-2",
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
    assert [event.id for event in query_trace_events(TraceQuery(session_id="session-2"))] == [
        "event-2",
        "event-3",
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
