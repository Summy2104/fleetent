"""Integration tests: traces and reflection are routed through agent_scope.

Verifies:
- agent_app boots agent_state.db via unified AGENT_STATE_MIGRATIONS
- traces.py exposes set_state_db() and uses the injected db for record/query
- reflection.py exposes set_state_db() and uses the injected db for operations
"""

from __future__ import annotations

import inspect
import sqlite3
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


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


# ── Positive invariants: agent_app uses unified migrations + agent_scope ──────


def test_agent_app_opens_agent_state_db_with_unified_migrations() -> None:
    """_init_agent_db_schema must open agent_state.db via agent_scope + AGENT_STATE_MIGRATIONS."""
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "router.agent_scope(tenant_id, agent_id).open_state_db(AGENT_STATE_MIGRATIONS)" in src, (
        "_init_agent_db_schema must bootstrap agent_state.db via "
        "router.agent_scope(...).open_state_db(AGENT_STATE_MIGRATIONS)"
    )


def test_agent_app_routes_traces_and_reflection_tables_to_agent_state_db(tmp_path: Path) -> None:
    """Boot on an empty management DB still creates runtime tables only in agent_state.db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    mgmt_db_path = data_dir / "management.db"

    _init_agent_db_schema(f"sqlite:///{mgmt_db_path}", agent_id="agent-1", tenant_id="default")

    agent_state_db_path = data_dir / "default" / "agent-1" / "agent_state.db"
    assert agent_state_db_path.exists()
    assert {"traces", "reflection_reports", "memory_items"} <= _tables(agent_state_db_path)
    if mgmt_db_path.exists():
        assert {"traces", "reflection_reports", "memory_items"}.isdisjoint(_tables(mgmt_db_path))


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


def test_traces_record_uses_injected_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_traces_query_uses_injected_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
