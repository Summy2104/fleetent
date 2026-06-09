"""Integration tests for session/index.py unified-store migration.

Verifies that:
1. session.index uses db.py (create_database) and not bare sqlite3.connect.
2. Data is written to the DATABASE_URL-pointed DB, never to users.db.
3. ensure_schema(db) is exposed and idempotent.
4. record_activity / get / list_by_user / count / total_message_count / delete all work
   against the unified DB.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase, create_database


def _db(tmp_path: Path) -> SQLiteDatabase:
    return SQLiteDatabase(path=tmp_path / "agent.db")


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'agent.db'}"


# ── ensure_schema ──────────────────────────────────────────────────────────────


def test_ensure_schema_is_exposed(tmp_path: Path) -> None:
    """session.index must export ensure_schema(db: SQLiteDatabase)."""
    from fleetent.session import index as session_index

    assert hasattr(session_index, "ensure_schema"), (
        "session.index must expose ensure_schema(); currently missing"
    )


def test_ensure_schema_creates_sessions_table(tmp_path: Path) -> None:
    from fleetent.session.index import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    row = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
    assert row is not None


def test_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.session.index import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    row = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
    assert row is not None


# ── no bare sqlite3 / no users.db ─────────────────────────────────────────────


def test_module_has_no_sqlite3_connect(tmp_path: Path) -> None:
    """session/index.py must not import or use sqlite3.connect."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "sqlite3.connect" not in src, (
        "session/index.py must not call sqlite3.connect — use db.py instead"
    )
    assert "users.db" not in src, (
        "session/index.py must not reference users.db — use DATABASE_URL / db.py"
    )


def test_no_sqlite3_import_in_module() -> None:
    """session/index.py must not import sqlite3 at all."""
    import fleetent.session.index as module

    src = inspect.getsource(module)
    assert "import sqlite3" not in src


# ── record_activity / get / list_by_user / count ──────────────────────────────


def test_record_activity_writes_to_unified_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """record_activity must write to the DATABASE_URL database, not users.db."""
    users_db = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))

    from fleetent.session.index import ensure_schema, record_activity

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
    record_activity("s1", "u1", 3, "my-agent")

    # Verify data is in the unified DB
    row = db.execute("SELECT session_id FROM sessions WHERE session_id = :sid", {"sid": "s1"}).fetchone()
    assert row is not None
    assert row["session_id"] == "s1"

    # users.db must NOT have been created
    assert not users_db.exists(), "users.db must not be created by session.index"


def test_get_returns_correct_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))
    from fleetent.session.index import ensure_schema, get, record_activity

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
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
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))
    from fleetent.session.index import ensure_schema, get

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
    assert get("nonexistent") is None


def test_list_by_user_returns_sessions_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))
    from fleetent.session.index import ensure_schema, list_by_user, record_activity

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
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
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))
    from fleetent.session.index import count, ensure_schema, record_activity

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
    assert count() == 0
    record_activity("sx", "u1", 1, "a")
    assert count() == 1


def test_delete_removes_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", _db_url(tmp_path))
    from fleetent.session.index import delete, ensure_schema, get, record_activity

    db = create_database(_db_url(tmp_path))
    ensure_schema(db)
    record_activity("sd", "u1", 1, "a")
    delete("sd")
    assert get("sd") is None
