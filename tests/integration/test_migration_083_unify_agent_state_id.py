"""Integration tests for migration 083 and the later session_meta retirement."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from fleetent import agent_store
from tests.integration._migration_template import apply_migrations


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _table_info(conn: sqlite3.Connection, table: str) -> dict[str, tuple[str, int]]:
    return {
        str(row[1]): (str(row[2]), int(row[5]))
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _fk_rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_schema_keeps_agent_admin_state_fk_and_drops_session_meta(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = sqlite3.connect(db)
    try:
        admin_state = _table_info(conn, "agent_admin_state")
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        admin_state_fks = _fk_rows(conn, "agent_admin_state")
    finally:
        conn.close()

    assert admin_state["agent_id"] == ("INTEGER", 1)
    assert "agent_name" not in admin_state
    assert "session_meta" not in tables

    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in admin_state_fks
    )


def test_upgrade_migrates_agent_name_keyed_admin_rows_and_then_drops_session_meta(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "082")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    support = agent_store.create_agent("support", "Support.", ["shell"])
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_admin_state
                (agent_name, status, provenance, drift, archived_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                support.name,
                "disabled",
                "managed",
                1,
                None,
                "2026-06-14T00:00:00+00:00",
                "ghost",
                "enabled",
                "adhoc",
                0,
                None,
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO session_meta
                (session_id, origin, status, pinned, agent_name, user_id, channel, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sess-support",
                "web",
                "active",
                0,
                support.name,
                "user-1",
                "slack:C1",
                "2026-06-14T00:00:00+00:00",
                "sess-ghost",
                "playground",
                "ended",
                1,
                "ghost",
                "user-2",
                None,
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        admin_rows = conn.execute(
            """
            SELECT agent_id, status
            FROM agent_admin_state
            ORDER BY agent_id
            """
        ).fetchall()
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert admin_rows == [(support.id, "disabled")]
    assert "session_meta" not in tables
    assert ops.id not in {row[0] for row in admin_rows}
