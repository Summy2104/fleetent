"""Integration tests: session/index.py connection comes from agent_scope (3b-1).

Verifies:
- session/index.py has no create_database(...) self-connect to global DB
- session/index.py has no sqlite3.connect
- connection is injected via set_state_db (called by agent boot wiring)
- after set_state_db, record_activity writes to the injected per-agent DB
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate
from fleetent.session.migrations import MIGRATIONS as SESSION_MIGRATIONS


# ── Guard: no self-connection in session/index.py ──────────────────────────


def test_session_index_has_no_create_database_call() -> None:
    """session/index.py must not call create_database() — it gets its DB injected."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "create_database(" not in src, (
        "session/index.py must not self-connect via create_database(); "
        "connection must come from agent_scope"
    )


def test_session_index_has_no_sqlite3_connect() -> None:
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "sqlite3.connect" not in src
    assert "import sqlite3" not in src


def test_session_index_has_no_database_url_self_resolve() -> None:
    """session/index.py must not read DATABASE_URL to create its own DB."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "DATABASE_URL" not in src, (
        "session/index.py must not read DATABASE_URL; "
        "DB must be injected via set_state_db"
    )


# ── set_state_db injection ─────────────────────────────────────────────────


def test_set_state_db_is_exposed() -> None:
    import fleetent.session.index as module

    assert hasattr(module, "set_state_db"), (
        "session.index must expose set_state_db(db: SQLiteDatabase)"
    )


def test_session_index_writes_to_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After set_state_db, record_activity writes to the injected per-agent DB."""
    import fleetent.session.index as session_index

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, SESSION_MIGRATIONS)
    monkeypatch.setattr(session_index, "_state_db", db)

    session_index.record_activity("s-inject", "u1", 3, "bot")
    row = db.execute(
        "SELECT session_id FROM sessions WHERE session_id = :sid", {"sid": "s-inject"}
    ).fetchone()
    assert row is not None
    assert row["session_id"] == "s-inject"


def test_session_index_get_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fleetent.session.index as session_index

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, SESSION_MIGRATIONS)
    monkeypatch.setattr(session_index, "_state_db", db)

    session_index.record_activity("s-get", "u1", 1, "bot")
    row = session_index.get("s-get")
    assert row is not None
    assert row["session_id"] == "s-get"


def test_session_index_raises_when_not_initialized() -> None:
    """_db() must raise (not silently fall back) when _state_db is None."""
    import fleetent.session.index as session_index

    # Temporarily clear _state_db
    original = session_index._state_db
    try:
        session_index._state_db = None
        with pytest.raises(RuntimeError):
            session_index._db()
    finally:
        session_index._state_db = original
