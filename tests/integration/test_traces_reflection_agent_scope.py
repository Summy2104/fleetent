"""Integration tests: traces and reflection connections come from agent_scope (3b-2).

Verifies:
- traces.py exposes set_state_db() and uses the injected db for record/query
- reflection.py exposes set_state_db() and uses the injected db for operations
- Guard: agent_app._init_agent_db_schema source no longer calls traces.ensure_schema
  or reflection.ensure_schema (schema now handled by unified AGENT_STATE_MIGRATIONS)
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate


def _open(tmp_path: Path, name: str = "agent_state.db") -> SQLiteDatabase:
    return SQLiteDatabase(path=tmp_path / name)


def _migrated_db(tmp_path: Path) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


# ── Guard: agent_app no longer calls ensure_schema into global db ──────────────


def test_agent_app_does_not_call_traces_ensure_schema() -> None:
    """_init_agent_db_schema must not call traces.ensure_schema (schema via Y now)."""
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "traces.ensure_schema" not in src, (
        "_init_agent_db_schema must not call traces.ensure_schema; "
        "traces schema is now bootstrapped via AGENT_STATE_MIGRATIONS"
    )


def test_agent_app_does_not_call_reflection_ensure_schema() -> None:
    """_init_agent_db_schema must not call reflection.ensure_schema (schema via Y now)."""
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "reflection.ensure_schema" not in src, (
        "_init_agent_db_schema must not call reflection.ensure_schema; "
        "reflection schema is now bootstrapped via AGENT_STATE_MIGRATIONS"
    )


def test_agent_app_calls_traces_set_state_db() -> None:
    """_init_agent_db_schema must wire the per-agent state_db into traces."""
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "traces.set_state_db" in src, (
        "_init_agent_db_schema must call traces.set_state_db(agent_state_db)"
    )


def test_agent_app_calls_reflection_set_state_db() -> None:
    """_init_agent_db_schema must wire the per-agent state_db into reflection."""
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "reflection.set_state_db" in src, (
        "_init_agent_db_schema must call reflection.set_state_db(agent_state_db)"
    )


# ── traces: set_state_db injection ────────────────────────────────────────────


def test_traces_exposes_set_state_db() -> None:
    from fleetent.observability import traces

    assert hasattr(traces, "set_state_db"), "traces must expose set_state_db(db: SQLiteDatabase)"
    assert callable(traces.set_state_db)


def test_traces_record_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After set_state_db, record_trace_event writes to the injected per-agent DB."""
    from fleetent.observability import traces
    from fleetent.observability.traces import TraceEvent

    db = _migrated_db(tmp_path)
    monkeypatch.setattr(traces, "_state_db", db)

    traces.record_trace_event(
        TraceEvent(run_id="run-inject", event_type="agent_run_completed", payload={"ok": True})
    )

    row = db.execute(
        "SELECT run_id FROM traces WHERE run_id = :rid", {"rid": "run-inject"}
    ).fetchone()
    assert row is not None
    assert row["run_id"] == "run-inject"


def test_traces_query_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query_trace_events reads from the injected per-agent DB."""
    from fleetent.observability import traces
    from fleetent.observability.traces import TraceEvent, TraceQuery

    db = _migrated_db(tmp_path)
    monkeypatch.setattr(traces, "_state_db", db)

    traces.record_trace_event(
        TraceEvent(run_id="run-query", event_type="tool_call", payload={"tool": "x"})
    )
    events = list(traces.query_trace_events(TraceQuery(run_id="run-query")))
    assert len(events) == 1
    assert events[0].run_id == "run-query"


# ── reflection: set_state_db injection ───────────────────────────────────────


def test_reflection_exposes_set_state_db() -> None:
    from fleetent import reflection

    assert hasattr(reflection, "set_state_db"), (
        "reflection must expose set_state_db(db: SQLiteDatabase)"
    )
    assert callable(reflection.set_state_db)


def test_reflection_database_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After set_state_db, reflection._database() returns the injected per-agent DB."""
    from fleetent import reflection

    db = _migrated_db(tmp_path)
    monkeypatch.setattr(reflection, "_state_db", db)

    returned = reflection._database()
    assert returned.path == db.path, (
        "reflection._database() must return the injected state_db when set"
    )
