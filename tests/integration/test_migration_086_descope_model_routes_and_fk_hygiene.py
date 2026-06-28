"""Integration tests for descope-model-routes-and-fk-hygiene migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.integration._migration_template import apply_migrations

_LEGACY_CHANNEL_BINDINGS_TABLE = "channel" + "_agents"


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _fk_rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def _fk_delete_action(
    conn: sqlite3.Connection, table: str, from_column: str, target_table: str
) -> str | None:
    for row in _fk_rows(conn, table):
        if row[2] == target_table and row[3] == from_column:
            return str(row[6])
    return None


def _insert_user(conn: sqlite3.Connection, user_id: str, *, tenant_id: str) -> None:
    conn.execute(
        """
        INSERT INTO users (id, name, created_at, role, status, must_reset, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, user_id.title(), "2026-06-14T00:00:00+00:00", "viewer", "active", 0, tenant_id),
    )


def _insert_agent(
    conn: sqlite3.Connection, name: str, *, tenant_id: str, team_id: str | None
) -> int:
    conn.execute(
        """
        INSERT INTO agents
            (name, system_prompt, allowed_tools, created_at, tenant_id, team_id, config_overrides)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, "sys", "[]", "2026-06-14T00:00:00+00:00", tenant_id, team_id, "{}"),
    )
    row = conn.execute("SELECT id FROM agents WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def test_head_schema_drops_legacy_route_table_and_index(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    legacy_route_table = "model" + "_routes"
    legacy_route_index = "idx_" + legacy_route_table + "_task"
    conn = _connect(db)
    try:
        tables = _tables(conn)
        provider_indexes = _indexes(conn, "model_providers")
    finally:
        conn.close()

    assert legacy_route_table not in tables
    assert legacy_route_index not in provider_indexes


def test_head_schema_sets_expected_fk_delete_actions_and_preserves_agent_shape(
    tmp_path: Path,
) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = _connect(db)
    try:
        agent_columns = _columns(conn, "agents")
        agent_indexes = _indexes(conn, "agents")
        child_fk_tables = [
            "agent_admin_state",
            "agent_kbs",
            "agent_mcp_servers",
            "agent_secrets",
            "agent_skills",
            "mcp_servers",
            "session_meta",
            "user_agents",
        ]
        child_delete_actions = {
            table: _fk_delete_action(conn, table, "agent_id", "agents") for table in child_fk_tables
        }
    finally:
        conn.close()

    assert _fk_delete_action(conn := _connect(db), "users", "tenant_id", "tenants") == "RESTRICT"
    conn.close()
    assert _fk_delete_action(conn := _connect(db), "agents", "tenant_id", "tenants") == "RESTRICT"
    conn.close()
    assert _fk_delete_action(conn := _connect(db), "agents", "team_id", "teams") == "RESTRICT"
    conn.close()
    assert _fk_delete_action(conn := _connect(db), "teams", "tenant_id", "tenants") == "RESTRICT"
    conn.close()
    assert (
        _fk_delete_action(conn := _connect(db), "tenants", "approver_user_id", "users")
        == "SET NULL"
    )
    conn.close()
    assert (
        _fk_delete_action(conn := _connect(db), "teams", "approver_user_id", "users") == "SET NULL"
    )
    conn.close()

    assert agent_columns >= {
        "id",
        "name",
        "system_prompt",
        "allowed_tools",
        "created_at",
        "tenant_id",
        "team_id",
        "version",
        "model_overrides",
        "memory_namespace",
        "skills_dir",
        "features",
        "plugins",
        "allowed_skills",
        "icon",
        "config_overrides",
    }
    assert "sqlite_autoindex_agents_1" in agent_indexes  # UNIQUE(name)
    assert child_delete_actions == {table: "CASCADE" for table in child_delete_actions}

    conn = _connect(db)
    try:
        assert _LEGACY_CHANNEL_BINDINGS_TABLE not in _tables(conn)
    finally:
        conn.close()


def test_delete_tenant_with_children_is_restricted(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = _connect(db)
    try:
        conn.execute(
            """
            INSERT INTO tenants (id, name, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("corp", "Corp", "active", "2026-06-14T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO teams (id, tenant_id, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("ops", "corp", "Ops", "2026-06-14T00:00:00+00:00"),
        )
        _insert_user(conn, "u-corp", tenant_id="corp")
        _insert_agent(conn, "corp-agent", tenant_id="corp", team_id="ops")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM tenants WHERE id = ?", ("corp",))
    finally:
        conn.close()


def test_delete_team_referenced_by_agent_is_restricted(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = _connect(db)
    try:
        conn.execute(
            """
            INSERT INTO teams (id, tenant_id, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("support", "default", "Support", "2026-06-14T00:00:00+00:00"),
        )
        _insert_agent(conn, "support-agent", tenant_id="default", team_id="support")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM teams WHERE id = ?", ("support",))
    finally:
        conn.close()


def test_delete_approver_user_sets_approver_columns_null(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = _connect(db)
    try:
        _insert_user(conn, "approver-1", tenant_id="default")
        conn.execute(
            """
            INSERT INTO tenants (id, name, status, created_at, approver_user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("tenant-a", "Tenant A", "active", "2026-06-14T00:00:00+00:00", "approver-1"),
        )
        conn.execute(
            """
            INSERT INTO teams (id, tenant_id, name, created_at, approver_user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("team-a", "default", "Team A", "2026-06-14T00:00:00+00:00", "approver-1"),
        )
        conn.commit()

        conn.execute("DELETE FROM users WHERE id = ?", ("approver-1",))
        conn.commit()

        tenant_approver = conn.execute(
            "SELECT approver_user_id FROM tenants WHERE id = ?", ("tenant-a",)
        ).fetchone()
        team_approver = conn.execute(
            "SELECT approver_user_id FROM teams WHERE id = ?", ("team-a",)
        ).fetchone()
        user_row = conn.execute("SELECT id FROM users WHERE id = ?", ("approver-1",)).fetchone()
    finally:
        conn.close()

    assert tenant_approver == (None,)
    assert team_approver == (None,)
    assert user_row is None
