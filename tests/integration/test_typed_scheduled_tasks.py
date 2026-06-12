"""Typed scheduled tasks: schema (task_type/notify_text) + store validation.

notify/generate/action typing with a frozen notify_text, defaulting to generate for
back-compat. See change typed-scheduled-task-delivery.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate


def _migrated(tmp_path: Path) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    return db


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def test_migration_adds_task_type_and_notify_text(tmp_path: Path) -> None:
    db = _migrated(tmp_path)
    cols = _columns(db.path, "scheduled_tasks")
    assert {"task_type", "notify_text"} <= cols


def test_legacy_row_defaults_to_generate(tmp_path: Path) -> None:
    db = _migrated(tmp_path)
    # A row inserted without task_type (older caller shape) defaults to 'generate'.
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks (id, schedule_kind, enabled) VALUES ('t', 'cron', 1)"
        )
    row = db.execute("SELECT task_type FROM scheduled_tasks WHERE id='t'").fetchone()
    assert row["task_type"] == "generate"


def test_store_create_notify_persists_frozen_copy(tmp_path: Path) -> None:
    from fleetent import schedule_store

    schedule_store.set_state_db(_migrated(tmp_path))
    task = schedule_store.create(
        name="晨会",
        schedule_kind="cron",
        cron_expr="0 9 * * 1-5",
        task_type="notify",
        notify_text="📅 晨会提醒：9:00 准时开始",
        deliver={"mode": "explicit", "platform": "slack", "target": "C1", "target_type": "channel"},
    )
    assert task["task_type"] == "notify"
    assert task["notify_text"] == "📅 晨会提醒：9:00 准时开始"
    got = schedule_store.get(task["id"])
    assert got["task_type"] == "notify"
    assert got["notify_text"] == "📅 晨会提醒：9:00 准时开始"


def test_store_create_notify_without_text_rejected(tmp_path: Path) -> None:
    from fleetent import schedule_store

    schedule_store.set_state_db(_migrated(tmp_path))
    with pytest.raises(ValueError):
        schedule_store.create(
            name="x", schedule_kind="cron", cron_expr="0 9 * * *", task_type="notify"
        )


def test_store_create_defaults_to_generate(tmp_path: Path) -> None:
    from fleetent import schedule_store

    schedule_store.set_state_db(_migrated(tmp_path))
    task = schedule_store.create(
        name="x", schedule_kind="cron", cron_expr="0 9 * * *", message="do"
    )
    assert task["task_type"] == "generate"
