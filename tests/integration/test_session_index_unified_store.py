"""Integration tests for session/index.py agent-scope migration (3b-1).

Verifies that after migrating from ensure_schema-into-global to agent_scope:
1. session.index has no bare sqlite3.connect and no DATABASE_URL self-resolve.
2. Data is written to the injected per-agent DB, never to users.db.
3. record_activity / get / list_by_user / count / delete all work against the
   injected DB.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate
from fleetent.session.migrations import MIGRATIONS as SESSION_MIGRATIONS


def _setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLiteDatabase:
    """Create and inject a fresh per-agent state DB."""
    import fleetent.session.index as session_index

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, SESSION_MIGRATIONS)
    monkeypatch.setattr(session_index, "_state_db", db)
    return db


# ── no bare sqlite3 / no DATABASE_URL self-resolve ───────────────────────


def test_module_has_no_sqlite3_connect() -> None:
    """session/index.py must not call sqlite3.connect or import sqlite3."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "sqlite3.connect" not in src, (
        "session/index.py must not call sqlite3.connect — use db.py instead"
    )
    assert "users.db" not in src, (
        "session/index.py must not reference users.db"
    )


def test_no_sqlite3_import_in_module() -> None:
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "import sqlite3" not in src


def test_no_create_database_self_connect() -> None:
    """session/index.py must not self-connect via create_database()."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "create_database(" not in src


def test_no_database_url_self_resolve() -> None:
    """session/index.py must not read DATABASE_URL to build its own connection."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "DATABASE_URL" not in src


# ── record_activity / get / list_by_user / count / delete ─────────────────


def test_record_activity_writes_to_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """record_activity must write to the injected per-agent DB, not users.db."""
    users_db = tmp_path / "users.db"
    db = _setup_db(tmp_path, monkeypatch)

    from fleetent.session.index import record_activity

    record_activity("s1", "u1", 3, "my-agent")

    row = db.execute(
        "SELECT session_id FROM sessions WHERE session_id = :sid", {"sid": "s1"}
    ).fetchone()
    assert row is not None
    assert row["session_id"] == "s1"
    assert not users_db.exists(), "users.db must not be created by session.index"


def test_get_returns_correct_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_db(tmp_path, monkeypatch)
    from fleetent.session.index import get, record_activity

    record_activity("s2", "user-x", 5, "bot")
    meta = get("s2")
    assert meta is not None
    assert meta["session_id"] == "s2"
    assert meta["user_id"] == "user-x"
    assert meta["message_count"] == 5
    assert meta["agent_name"] == "bot"


def test_get_returns_none_for_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_db(tmp_path, monkeypatch)
    from fleetent.session.index import get

    assert get("nonexistent") is None


def test_list_by_user_returns_sessions_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_db(tmp_path, monkeypatch)
    from fleetent.session.index import list_by_user, record_activity

    record_activity("old", "u1", 1, "a")
    time.sleep(0.01)
    record_activity("new", "u1", 2, "a")

    results = list_by_user("u1")
    assert len(results) == 2
    assert results[0]["session_id"] == "new"
    assert results[1]["session_id"] == "old"


def test_count_reflects_recorded_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_db(tmp_path, monkeypatch)
    from fleetent.session.index import count, record_activity

    assert count() == 0
    record_activity("sx", "u1", 1, "a")
    assert count() == 1


def test_delete_removes_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_db(tmp_path, monkeypatch)
    from fleetent.session.index import delete, get, record_activity

    record_activity("sd", "u1", 1, "a")
    delete("sd")
    assert get("sd") is None
