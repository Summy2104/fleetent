"""Integration tests: schedule_store injection contract (retire-standalone-fleetent-db).

Verifies:
1. set_state_db(db) routes CRUD through the injected agent_state.db.
2. CRUD without injection raises RuntimeError (same pattern as sub_agent_lifecycle).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate


def _open_agent_state_db(tmp_path: Path) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


@pytest.fixture
def _reset_schedule_store_state_db():
    """Restore schedule_store._state_db after each test."""
    import fleetent.schedule_store as ss

    original = ss._state_db
    yield
    ss._state_db = original


# ── 1: injection routes CRUD through injected DB ──────────────────────────────


def test_create_uses_injected_db(tmp_path: Path, _reset_schedule_store_state_db: None) -> None:
    import fleetent.schedule_store as ss

    db = _open_agent_state_db(tmp_path)
    ss.set_state_db(db)

    task = ss.create(name="daily", cron_expr="0 9 * * 1-5", user_id="u-1", message="run report")
    assert isinstance(task["id"], str) and len(task["id"]) == 36
    assert task["name"] == "daily"

    row = db.execute("SELECT id FROM scheduled_tasks WHERE id = :id", {"id": task["id"]}).fetchone()
    assert row is not None


def test_list_tasks_uses_injected_db(tmp_path: Path, _reset_schedule_store_state_db: None) -> None:
    import fleetent.schedule_store as ss

    db = _open_agent_state_db(tmp_path)
    ss.set_state_db(db)

    ss.create(name="a", cron_expr="* * * * *", user_id="u-1", message="msg-a")
    ss.create(name="b", cron_expr="0 0 * * *", user_id="u-2", message="msg-b")
    tasks = ss.list_tasks()
    assert len(tasks) == 2
    assert {t["name"] for t in tasks} == {"a", "b"}


def test_delete_uses_injected_db(tmp_path: Path, _reset_schedule_store_state_db: None) -> None:
    import fleetent.schedule_store as ss

    db = _open_agent_state_db(tmp_path)
    ss.set_state_db(db)

    task = ss.create(name="x", cron_expr="* * * * *", user_id="u-1", message="msg")
    deleted = ss.delete(task["id"])
    assert deleted is True
    assert ss.list_tasks() == []


# ── 2: no injection raises RuntimeError ───────────────────────────────────────


def test_create_without_injection_raises(tmp_path: Path, _reset_schedule_store_state_db: None) -> None:
    import fleetent.schedule_store as ss

    ss._state_db = None  # explicitly ensure uninitialised

    with pytest.raises(RuntimeError, match="set_state_db"):
        ss.create(name="z", cron_expr="* * * * *", user_id="u-1", message="msg")


def test_list_tasks_without_injection_raises(
    tmp_path: Path, _reset_schedule_store_state_db: None
) -> None:
    import fleetent.schedule_store as ss

    ss._state_db = None

    with pytest.raises(RuntimeError, match="set_state_db"):
        ss.list_tasks()


def test_delete_without_injection_raises(
    tmp_path: Path, _reset_schedule_store_state_db: None
) -> None:
    import fleetent.schedule_store as ss

    ss._state_db = None

    with pytest.raises(RuntimeError, match="set_state_db"):
        ss.delete("00000000-0000-0000-0000-000000000000")
