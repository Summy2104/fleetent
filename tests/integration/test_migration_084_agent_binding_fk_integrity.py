"""Integration tests for migration 084: MCP rename + agent binding FK integrity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from fleetent import agent_store
from tests.integration._migration_template import apply_migrations

_LEGACY_CHANNEL_BINDINGS_TABLE = "channel" + "_agents"


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _fk_rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_schema_renames_mcp_tables_and_index(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        mcp_server_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(mcp_servers)").fetchall()
        }
        binding_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(agent_mcp_servers)").fetchall()
        }
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(mcp_servers)").fetchall()}
    finally:
        conn.close()

    assert "mcp_servers" in tables
    assert "agent_mcp_servers" in tables
    assert "agent_mcp_server_bindings" not in tables
    assert mcp_server_cols >= {
        "id",
        "agent_id",
        "server_id",
        "transport",
        "url",
        "auth_type",
        "api_key_env",
        "command",
        "args",
        "env",
        "headers",
        "enabled",
        "created_at",
    }
    assert binding_cols >= {"agent_id", "server_id", "created_at", "created_by"}
    assert "idx_mcp_servers_agent" in indexes


def test_upgrade_preserves_mcp_registry_and_binding_rows_across_rename(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "083")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_mcp_servers
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
        conn.execute(
            """
            INSERT INTO agent_mcp_servers
                (agent_id, server_id, transport, url, auth_type, api_key_env,
                 command, args, env, created_at, enabled, headers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "jira",
                "http",
                "https://jira.example/mcp",
                "none",
                "",
                "",
                None,
                None,
                "2026-06-14T00:00:00+00:00",
                1,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_mcp_server_bindings (agent_id, server_id, created_at, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (agent.id, "github", "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        registry_rows = conn.execute(
            """
            SELECT agent_id, server_id, transport, command, url
            FROM mcp_servers
            ORDER BY server_id
            """
        ).fetchall()
        binding_rows = conn.execute(
            """
            SELECT agent_id, server_id, created_by
            FROM agent_mcp_servers
            ORDER BY server_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert registry_rows == [
        (agent.id, "github", "stdio", "npx", ""),
        (None, "jira", "http", "", "https://jira.example/mcp"),
    ]
    assert binding_rows == [(agent.id, "github", "seed")]


def test_head_schema_adds_agent_fk_cascades_to_binding_tables_only(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        user_agents_fks = _fk_rows(conn, "user_agents")
        agent_versions_fks = _fk_rows(conn, "agent_versions")
        mcp_servers_fks = _fk_rows(conn, "mcp_servers")
        agent_secrets_fks = _fk_rows(conn, "agent_secrets")
        external_services_fks = _fk_rows(conn, "external_services")
    finally:
        conn.close()

    for fk_rows in [user_agents_fks, agent_versions_fks, mcp_servers_fks, agent_secrets_fks]:
        assert any(
            row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
            for row in fk_rows
        )
    assert external_services_fks == []
    assert _LEGACY_CHANNEL_BINDINGS_TABLE not in tables


def test_upgrade_cleans_orphans_and_agent_delete_cascades_bindings(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "083")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    agent_store.create_version("ops", system_prompt="Ops v2")

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO user_agents (user_id, agent_id) VALUES (?, ?), (?, ?)",
            ("u-live", agent.id, "u-orphan", 999999),
        )
        conn.execute(
            """
            INSERT INTO {_LEGACY_CHANNEL_BINDINGS_TABLE}
                (platform, channel_id, agent_id, created_at, bound_version_id)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """.replace("{_LEGACY_CHANNEL_BINDINGS_TABLE}", _LEGACY_CHANNEL_BINDINGS_TABLE),
            (
                "slack",
                "C-live",
                agent.id,
                "2026-06-14T00:00:00+00:00",
                None,
                "slack",
                "C-orphan",
                999999,
                "2026-06-14T00:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_mcp_servers
                (agent_id, server_id, transport, url, auth_type, api_key_env,
                 command, args, env, created_at, enabled, headers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?),
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent.id,
                "github",
                "http",
                "https://github.example/mcp",
                "bearer",
                "GH_TOKEN",
                "",
                None,
                None,
                "2026-06-14T00:00:00+00:00",
                1,
                None,
                999999,
                "ghost",
                "http",
                "https://ghost.example/mcp",
                "none",
                "",
                "",
                None,
                None,
                "2026-06-14T00:00:00+00:00",
                1,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_mcp_server_bindings (agent_id, server_id, created_at, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (agent.id, "github", "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.execute(
            """
            INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """,
            (
                agent.id,
                "LIVE_SECRET",
                "ciphertext-live",
                "2026-06-14T00:00:00+00:00",
                "seed",
                999999,
                "ORPHAN_SECRET",
                "ciphertext-orphan",
                "2026-06-14T00:00:00+00:00",
                "seed",
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_versions
                (agent_id, version, system_prompt, allowed_tools, skills_dir, mcp_server_ids,
                 model_overrides, memory_namespace, created_by_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                999999,
                1,
                "ghost",
                "[]",
                None,
                None,
                "{}",
                "default",
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
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        live_counts = {
            "user_agents": conn.execute(
                "SELECT COUNT(*) FROM user_agents WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_versions": conn.execute(
                "SELECT COUNT(*) FROM agent_versions WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "mcp_servers": conn.execute(
                "SELECT COUNT(*) FROM mcp_servers WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_mcp_servers": conn.execute(
                "SELECT COUNT(*) FROM agent_mcp_servers WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_secrets": conn.execute(
                "SELECT COUNT(*) FROM agent_secrets WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
        }
        orphan_counts = {
            "user_agents": conn.execute(
                "SELECT COUNT(*) FROM user_agents WHERE agent_id = 999999"
            ).fetchone()[0],
            "agent_versions": conn.execute(
                "SELECT COUNT(*) FROM agent_versions WHERE agent_id = 999999"
            ).fetchone()[0],
            "mcp_servers": conn.execute(
                "SELECT COUNT(*) FROM mcp_servers WHERE agent_id = 999999"
            ).fetchone()[0],
            "agent_secrets": conn.execute(
                "SELECT COUNT(*) FROM agent_secrets WHERE agent_id = 999999"
            ).fetchone()[0],
        }
    finally:
        conn.close()

    assert agent_store.delete_agent("ops") is True

    conn = sqlite3.connect(db)
    try:
        post_delete_counts = {
            "user_agents": conn.execute(
                "SELECT COUNT(*) FROM user_agents WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_versions": conn.execute(
                "SELECT COUNT(*) FROM agent_versions WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "mcp_servers": conn.execute(
                "SELECT COUNT(*) FROM mcp_servers WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_mcp_servers": conn.execute(
                "SELECT COUNT(*) FROM agent_mcp_servers WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
            "agent_secrets": conn.execute(
                "SELECT COUNT(*) FROM agent_secrets WHERE agent_id = ?", (agent.id,)
            ).fetchone()[0],
        }
    finally:
        conn.close()

    assert _LEGACY_CHANNEL_BINDINGS_TABLE not in tables
    assert live_counts == {
        "user_agents": 1,
        "agent_versions": 2,
        "mcp_servers": 1,
        "agent_mcp_servers": 1,
        "agent_secrets": 1,
    }
    assert orphan_counts == {
        "user_agents": 0,
        "agent_versions": 0,
        "mcp_servers": 0,
        "agent_secrets": 0,
    }
    assert post_delete_counts == {
        "user_agents": 0,
        "agent_versions": 0,
        "mcp_servers": 0,
        "agent_mcp_servers": 0,
        "agent_secrets": 0,
    }
