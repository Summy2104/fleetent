"""Integration tests for platform integrity cleanup migration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def _config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _upgrade_to(db_path: Path, revision: str) -> None:
    command.upgrade(_config(db_path), revision)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed_tenant(conn: sqlite3.Connection, tenant_id: str) -> None:
    conn.execute(
        """
        INSERT INTO tenants (id, name, status, created_at, approver_user_id)
        VALUES (?, ?, 'active', '2026-06-28T00:00:00+00:00', NULL)
        """,
        (tenant_id, tenant_id.upper()),
    )


def _seed_team(conn: sqlite3.Connection, team_id: str, tenant_id: str) -> None:
    conn.execute(
        """
        INSERT INTO teams (id, tenant_id, name, approver_user_id, created_at)
        VALUES (?, ?, ?, NULL, '2026-06-28T00:00:00+00:00')
        """,
        (team_id, tenant_id, f"{team_id}-team"),
    )


def _seed_user(conn: sqlite3.Connection, user_id: str, tenant_id: str = "default") -> None:
    conn.execute(
        """
        INSERT INTO users (id, name, created_at, email, tenant_id)
        VALUES (?, ?, '2026-06-28T00:00:00+00:00', NULL, ?)
        """,
        (user_id, user_id, tenant_id),
    )


def _seed_agent(
    conn: sqlite3.Connection,
    *,
    agent_id: int,
    name: str,
    tenant_id: str,
    team_id: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO agents (
            id,
            name,
            version,
            system_prompt,
            allowed_tools,
            features,
            plugins,
            allowed_skills,
            created_at,
            tenant_id,
            team_id,
            skills_dir,
            model_overrides,
            memory_namespace,
            icon,
            config_overrides
        )
        VALUES (?, ?, 1, 'prompt', '[]', '{}', '[]', '[]', '2026-06-28T00:00:00+00:00', ?, ?, NULL, '{}', 'default', NULL, '{}')
        """,
        (agent_id, name, tenant_id, team_id),
    )


def _seed_api_key(conn: sqlite3.Connection, *, user_id: str, suffix: str) -> None:
    plaintext = f"ma-{suffix * 32}"[:67]
    conn.execute(
        """
        INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at, call_count)
        VALUES (?, ?, ?, ?, '2026-06-28T00:00:00+00:00', 0)
        """,
        (user_id, f"hash-{suffix}", plaintext[:11], json.dumps(["*"])),
    )


def _unique_indexes(conn: sqlite3.Connection, table: str) -> dict[str, tuple[str, ...]]:
    indexes: dict[str, tuple[str, ...]] = {}
    for row in conn.execute(f"PRAGMA index_list({table})"):
        if not row["unique"]:
            continue
        indexes[str(row["name"])] = tuple(
            str(col["name"])
            for col in conn.execute(f"PRAGMA index_info({row['name']})")
            if col["name"] is not None
        )
    return indexes


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_migration_deletes_orphan_api_keys(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "105")

    with _connect(db) as conn:
        _seed_api_key(conn, user_id="ghost-user", suffix="a")
        conn.commit()

    _upgrade_to(db, "head")

    with _connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM api_keys").fetchone()["count"]

    assert count == 0


def test_head_migration_fails_loud_on_cross_tenant_team_reference(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "105")

    with _connect(db) as conn:
        _seed_tenant(conn, "tenant-a")
        _seed_tenant(conn, "tenant-b")
        _seed_team(conn, "team-b", "tenant-b")
        _seed_agent(conn, agent_id=1, name="ops", tenant_id="tenant-a", team_id="team-b")
        conn.commit()

    with pytest.raises(Exception, match="ops|team-b|tenant-a|tenant-b"):
        _upgrade_to(db, "head")


def test_head_schema_enforces_team_tenant_fk_and_api_key_cascade(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "105")

    with _connect(db) as conn:
        _seed_tenant(conn, "tenant-a")
        _seed_tenant(conn, "tenant-b")
        _seed_team(conn, "shared", "tenant-a")
        _seed_team(conn, "shared-b", "tenant-b")
        _seed_user(conn, "user-1", tenant_id="tenant-a")
        _seed_api_key(conn, user_id="user-1", suffix="b")
        _seed_agent(conn, agent_id=1, name="ops", tenant_id="tenant-a", team_id="shared")
        conn.commit()

    _upgrade_to(db, "head")

    with _connect(db) as conn:
        team_indexes = _unique_indexes(conn, "teams")
        agent_fks = _foreign_keys(conn, "agents")
        api_key_fks = _foreign_keys(conn, "api_keys")

        assert ("id", "tenant_id") in team_indexes.values()
        assert any(
            row["table"] == "teams"
            and row["from"] == "team_id"
            and row["to"] == "id"
            and row["on_delete"].upper() == "RESTRICT"
            for row in agent_fks
        )
        assert any(
            row["table"] == "teams"
            and row["from"] == "tenant_id"
            and row["to"] == "tenant_id"
            and row["on_delete"].upper() == "RESTRICT"
            for row in agent_fks
        )
        assert any(
            row["table"] == "users"
            and row["from"] == "user_id"
            and row["to"] == "id"
            and row["on_delete"].upper() == "CASCADE"
            for row in api_key_fks
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO agents (
                    id,
                    name,
                    version,
                    system_prompt,
                    allowed_tools,
                    features,
                    plugins,
                    allowed_skills,
                    created_at,
                    tenant_id,
                    team_id,
                    skills_dir,
                    model_overrides,
                    memory_namespace,
                    icon,
                    config_overrides
                )
                VALUES (
                    2,
                    'cross-tenant',
                    1,
                    'prompt',
                    '[]',
                    '{}',
                    '[]',
                    '[]',
                    '2026-06-28T00:00:00+00:00',
                    'tenant-a',
                    'shared-b',
                    NULL,
                    '{}',
                    'default',
                    NULL,
                    '{}'
                )
                """
            )

        before = conn.execute("SELECT COUNT(*) AS count FROM api_keys WHERE user_id = 'user-1'").fetchone()
        assert before is not None and before["count"] == 1
        conn.execute("DELETE FROM users WHERE id = 'user-1'")
        after = conn.execute("SELECT COUNT(*) AS count FROM api_keys WHERE user_id = 'user-1'").fetchone()
        assert after is not None and after["count"] == 0
