"""Integration tests for migration 088: agent IM access scaffolding."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from fleetent import agent_store


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_head_schema_adds_agent_im_groups_and_im_capability_columns(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = _connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        group_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(agent_im_groups)").fetchall()
        }
        agent_cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        group_indexes = conn.execute("PRAGMA index_list(agent_im_groups)").fetchall()
        group_fks = conn.execute("PRAGMA foreign_key_list(agent_im_groups)").fetchall()
        support_defaults = {
            row[1]: row[4]
            for row in conn.execute("PRAGMA table_info(agents)").fetchall()
            if row[1] in {"supports_dm", "supports_groups"}
        }
    finally:
        conn.close()

    assert "agent_im_groups" in tables
    assert group_cols == {"agent_id", "platform", "group_id", "created_at", "created_by"}
    assert {"supports_dm", "supports_groups"} <= agent_cols
    assert support_defaults == {"supports_dm": "0", "supports_groups": "0"}
    assert any(index_row[2] for index_row in group_indexes)
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in group_fks
    )


def test_agent_delete_cascades_agent_im_group_rows(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])

    conn = _connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_im_groups (agent_id, platform, group_id, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent.id, "slack", "C0123", "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) FROM agent_im_groups WHERE agent_id = ?",
            (agent.id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert before == 1
    assert agent_store.delete_agent("ops") is True

    conn = _connect(db)
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM agent_im_groups WHERE agent_id = ?",
            (agent.id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert after == 0
