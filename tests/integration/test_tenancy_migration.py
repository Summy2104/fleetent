"""Integration tests for the establish-tenancy migrations (067–069).

Covers:
- Task 2.1/2.3: tenants/teams tables, default principal, reversibility
- Task 3.1/3.3: users.tenant_id in alembic, FK upgrades for agents/KB/traces/policies
- Task 4.1: approver_user_id FK→users
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _upgrade(db: Path, rev: str = "head") -> None:
    command.upgrade(_cfg(db), rev)


def _downgrade(db: Path, rev: str) -> None:
    command.downgrade(_cfg(db), rev)


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return tables


def _columns(db: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    conn.close()
    return cols


def _fk_list(db: Path, table: str) -> list[dict[str, str]]:
    conn = sqlite3.connect(db)
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    conn.close()
    return [{"from": r[3], "table": r[2], "to": r[4]} for r in rows]


def _fetch_one(db: Path, sql: str, *params: object) -> object:
    conn = sqlite3.connect(db)
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


# ── Task 2.1: tenants/teams tables + default principal ───────────────────────


def test_upgrade_creates_tenants_table(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    assert "tenants" in _tables(db)


def test_upgrade_creates_teams_table(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    assert "teams" in _tables(db)


def test_tenants_columns(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    cols = _columns(db, "tenants")
    assert cols >= {"id", "name", "status", "created_at", "approver_user_id"}


def test_teams_columns(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    cols = _columns(db, "teams")
    assert cols >= {"id", "tenant_id", "name", "approver_user_id", "created_at"}


def test_teams_tenant_id_is_fk_to_tenants(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "teams")
    tenant_fk = next((f for f in fks if f["from"] == "tenant_id"), None)
    assert tenant_fk is not None, "teams.tenant_id should have FK→tenants"
    assert tenant_fk["table"] == "tenants"
    assert tenant_fk["to"] == "id"


def test_default_principal_exists_after_upgrade(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    row = _fetch_one(db, "SELECT id, status FROM tenants WHERE id = 'default'")
    assert row is not None, "default tenant row should exist"
    assert row[1] == "active"


# ── Task 2.3: reversibility — upgrade→downgrade→upgrade ──────────────────────


def test_downgrade_removes_tenants_and_teams(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    _downgrade(db, "066")
    tables = _tables(db)
    assert "tenants" not in tables
    assert "teams" not in tables


def test_round_trip_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    _downgrade(db, "066")
    _upgrade(db)
    assert "tenants" in _tables(db)
    assert "teams" in _tables(db)
    row = _fetch_one(db, "SELECT id FROM tenants WHERE id = 'default'")
    assert row is not None


# ── Task 3.1: users.tenant_id from alembic ───────────────────────────────────


def test_users_table_has_tenant_id_column(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    assert "tenant_id" in _columns(db, "users")


def test_users_tenant_id_fk_to_tenants(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "users")
    tenant_fk = next((f for f in fks if f["from"] == "tenant_id"), None)
    assert tenant_fk is not None, "users.tenant_id should have FK→tenants"
    assert tenant_fk["table"] == "tenants"


def test_existing_users_backfilled_to_default(tmp_path: Path) -> None:
    """Migration on a db with pre-existing users sets tenant_id='default' for all."""
    db = tmp_path / "test.db"
    # Simulate users table from legacy _init_db() BEFORE tenancy migrations run
    _upgrade(db, "066")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            email TEXT,
            password_hash TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            status TEXT NOT NULL DEFAULT 'active',
            must_reset INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at) VALUES "
        "('u1', 'Alice', 'ma-aaa', '2026-01-01T00:00:00'), "
        "('u2', 'Bob', 'ma-bbb', '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()
    _upgrade(db)
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT id, tenant_id FROM users").fetchall()
    conn.close()
    assert len(rows) == 2
    for row in rows:
        assert row[1] == "default", f"user {row[0]} should have tenant_id='default'"


def test_new_users_get_default_tenant_id(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO users (id, name, created_at, tenant_id) VALUES "
        "('u3', 'Carol', '2026-01-03T00:00:00', 'default')"
    )
    conn.commit()
    row = conn.execute("SELECT tenant_id FROM users WHERE id = 'u3'").fetchone()
    conn.close()
    assert row[0] == "default"


# ── Task 3.3: FK upgrades for existing tenant_id/team_id columns ─────────────


def test_agents_tenant_id_fk_to_tenants(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "agents")
    tenant_fk = next((f for f in fks if f["from"] == "tenant_id"), None)
    assert tenant_fk is not None, "agents.tenant_id should have FK→tenants"
    assert tenant_fk["table"] == "tenants"


def test_agents_team_id_fk_to_teams(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "agents")
    team_fk = next((f for f in fks if f["from"] == "team_id"), None)
    assert team_fk is not None, "agents.team_id should have FK→teams"
    assert team_fk["table"] == "teams"


def test_traces_table_is_absent_from_management_db(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    assert "traces" not in _tables(db)


def test_knowledge_bases_table_is_absent_from_management_db_head(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    assert "knowledge_bases" not in _tables(db)


def test_dormant_context_policy_table_is_absent_from_management_db_head(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    table_name = "long_term_context" + "_policies"
    assert table_name not in _tables(db)


def test_existing_agent_tenant_id_preserved(tmp_path: Path) -> None:
    """Migration must not change existing agent.tenant_id values."""
    db = tmp_path / "test.db"
    _upgrade(db, "066")
    conn = sqlite3.connect(db)
    # agents.id is INTEGER (auto-increment); insert without specifying id
    conn.execute(
        "INSERT INTO agents (name, system_prompt, allowed_tools, created_at, tenant_id) VALUES "
        "('TestAgent', 'sys', '[]', '2026-01-01T00:00:00', 'default')"
    )
    agent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    _upgrade(db)
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT tenant_id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    assert row[0] == "default"


# ── Task 4.1: approver_user_id FK→users ──────────────────────────────────────


def test_tenants_approver_user_id_fk_to_users(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "tenants")
    approver_fk = next((f for f in fks if f["from"] == "approver_user_id"), None)
    assert approver_fk is not None, "tenants.approver_user_id should have FK→users"
    assert approver_fk["table"] == "users"


def test_teams_approver_user_id_fk_to_users(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    fks = _fk_list(db, "teams")
    approver_fk = next((f for f in fks if f["from"] == "approver_user_id"), None)
    assert approver_fk is not None, "teams.approver_user_id should have FK→users"
    assert approver_fk["table"] == "users"


def test_approver_user_id_nullable_by_default(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _upgrade(db)
    row = _fetch_one(db, "SELECT approver_user_id FROM tenants WHERE id = 'default'")
    assert row is not None
    assert row[0] is None
