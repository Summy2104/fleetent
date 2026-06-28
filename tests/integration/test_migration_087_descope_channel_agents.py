"""Integration tests for migration 087: drop the dead channel-route table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from fleetent import agent_store

_CHANNEL_BINDINGS_TABLE = "channel" + "_agents"


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_head_schema_drops_dead_channel_route_table(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = _connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert _CHANNEL_BINDINGS_TABLE not in tables


def test_agent_delete_still_cascades_remaining_bindings_without_dead_channel_route_table(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    agent_store.assign_user("u-live", agent.id)
    agent_store.update_agent_config("ops", system_prompt="Ops v2")
    agent_store.bind_mcp_server(agent.id, "github", created_by="seed")

    conn = _connect(db)
    try:
        conn.execute(
            """
            INSERT INTO mcp_servers
                (agent_id, server_id, transport, url, auth_type, api_key_env,
                 command, args, env, created_at, enabled, headers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent.id,
                "github",
                "stdio",
                "",
                "none",
                "",
                "npx",
                '["-y", "@modelcontextprotocol/server-github"]',
                None,
                "2026-06-14T00:00:00+00:00",
                1,
                None,
            ),
        )
        conn.commit()
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert _CHANNEL_BINDINGS_TABLE not in tables

    assert agent_store.delete_agent("ops") is True

    conn = _connect(db)
    try:
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0]
            for table in ("user_agents", "mcp_servers", "agent_mcp_servers")
        }
    finally:
        conn.close()

    assert counts == {
        "user_agents": 0,
        "mcp_servers": 0,
        "agent_mcp_servers": 0,
    }
