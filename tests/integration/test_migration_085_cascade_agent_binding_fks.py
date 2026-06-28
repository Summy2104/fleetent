"""Integration tests for migration 085: cascade FK on agent binding tables."""

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


def _fk_rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_schema_binding_tables_have_cascade_fk(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = sqlite3.connect(db)
    try:
        mcp_binding_fks = _fk_rows(conn, "agent_mcp_servers")
    finally:
        conn.close()

    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in mcp_binding_fks
    )


def test_upgrade_cleans_binding_orphans_and_preserves_live(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "084")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_mcp_servers (agent_id, server_id, created_at, created_by)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                agent.id,
                "github",
                "2026-06-14T00:00:00+00:00",
                "seed",
                999999,
                "ghost",
                "2026-06-14T00:00:00+00:00",
                "seed",
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_oauth_bindings (agent_id, connector_id, created_at, created_by)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                agent.id,
                "google-oauth",
                "2026-06-14T00:00:00+00:00",
                "seed",
                999999,
                "ghost-oauth",
                "2026-06-14T00:00:00+00:00",
                "seed",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        mcp_live = conn.execute(
            "SELECT COUNT(*) FROM agent_mcp_servers WHERE agent_id = ?", (agent.id,)
        ).fetchone()[0]
        mcp_orphan = conn.execute(
            "SELECT COUNT(*) FROM agent_mcp_servers WHERE agent_id = 999999"
        ).fetchone()[0]
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()

    assert (mcp_live, mcp_orphan) == (1, 0)
    assert "agent_service_grants" not in tables


def test_agent_delete_cascades_binding_rows_without_manual_clear(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    agent_store.bind_mcp_server(agent.id, "github")

    assert agent_store.delete_agent("ops") is True

    conn = sqlite3.connect(db)
    try:
        mcp = conn.execute(
            "SELECT COUNT(*) FROM agent_mcp_servers WHERE agent_id = ?", (agent.id,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert mcp == 0
