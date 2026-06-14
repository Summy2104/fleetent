"""Integration tests for migration 092: redesign skill schema + drift protection."""

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


def _downgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, revision)


def _table_info(conn: sqlite3.Connection, table: str) -> dict[str, tuple[str, int, str | None]]:
    return {
        str(row[1]): (str(row[2]), int(row[5]), row[4])
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def _fk_rows(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_schema_replaces_skill_provenance_with_skills_master_table(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        skills = _table_info(conn, "skills")
        agent_skills = _table_info(conn, "agent_skills")
    finally:
        conn.close()

    assert "skills" in tables
    assert "skill_provenance" not in tables
    assert "skill_admin_state" not in tables
    assert skills == {
        "name": ("TEXT", 1, None),
        "status": ("TEXT", 0, "'active'"),
        "global_enabled": ("INTEGER", 0, "'1'"),
        "audit_verdict": ("TEXT", 0, None),
        "audit_rules": ("TEXT", 0, None),
        "forced": ("INTEGER", 0, "'0'"),
        "source": ("TEXT", 0, "'adhoc'"),
        "immutable_fields": ("TEXT", 0, None),
        "current_version": ("TEXT", 0, None),
        "archived_at": ("TEXT", 0, None),
        "created_at": ("TEXT", 0, None),
        "updated_at": ("TEXT", 0, None),
    }
    assert agent_skills["base_version"] == ("TEXT", 0, None)
    assert agent_skills["drift"] == ("INTEGER", 0, "0")
    assert agent_skills["drift_at"] == ("TEXT", 0, None)


def test_upgrade_backfills_skills_from_state_and_provenance(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "091")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO skill_admin_state
                (
                    skill_name, status, global_enabled, audit_verdict,
                    audit_rules, forced, archived_at, updated_at
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?),
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "crm-ops",
                "active",
                1,
                "pass",
                '["safe"]',
                0,
                None,
                "2026-06-14T00:00:00+00:00",
                "billing",
                "quarantined",
                0,
                "rejected",
                '["rm -rf"]',
                1,
                None,
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO skill_provenance
                (skill_name, source, drift, immutable_fields, last_deploy_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?),
                (?, ?, ?, ?, ?, ?)
            """,
            (
                "crm-ops",
                "managed",
                1,
                '["name"]',
                "deprecated",
                "2026-06-14T00:00:00+00:00",
                "search",
                "managed",
                1,
                '["description"]',
                "deprecated",
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            """
            SELECT
                name, status, global_enabled, audit_verdict,
                audit_rules, forced, source, immutable_fields
            FROM skills
            ORDER BY name
            """
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("billing", "quarantined", 0, "rejected", '["rm -rf"]', 1, "adhoc", None),
        ("crm-ops", "active", 1, "pass", '["safe"]', 0, "managed", '["name"]'),
        ("search", "active", 1, None, None, 0, "managed", '["description"]'),
    ]


def test_upgrade_initializes_agent_skill_drift_to_zero_and_preserves_agent_fk(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "091")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("support", "Support.", ["shell"])
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_skills (agent_id, skill_name, enabled, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent.id, "crm-ops", 1, "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.execute(
            """
            INSERT INTO skill_provenance
                (skill_name, source, drift, immutable_fields, last_deploy_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "crm-ops",
                "managed",
                1,
                None,
                "2026-06-14T00:00:00+00:00",
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT agent_id, skill_name, enabled, base_version, drift, drift_at FROM agent_skills"
        ).fetchall()
        fks = _fk_rows(conn, "agent_skills")
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert rows == [(agent.id, "crm-ops", 1, None, 0, None)]
    assert "skill_provenance" not in tables
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in fks
    )


def test_upgrade_backfills_catalog_rows_for_bound_skills_and_adds_skill_fk(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "091")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("support", "Support.", ["shell"])
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_skills (agent_id, skill_name, enabled, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent.id, "uncataloged-skill", 1, "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        skill_row = conn.execute(
            "SELECT name, status, global_enabled, source FROM skills WHERE name = ?",
            ("uncataloged-skill",),
        ).fetchone()
        fks = _fk_rows(conn, "agent_skills")
    finally:
        conn.close()

    assert skill_row == ("uncataloged-skill", "active", 1, "adhoc")
    assert any(
        row[2] == "skills" and row[3] == "skill_name" and row[4] == "name" for row in fks
    )


def test_downgrade_restores_legacy_skill_tables_and_removes_agent_skill_drift_columns(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "091")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("support", "Support.", ["shell"])
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO skill_admin_state
                (
                    skill_name, status, global_enabled, audit_verdict,
                    audit_rules, forced, archived_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "crm-ops",
                "quarantined",
                0,
                "rejected",
                '["rule"]',
                1,
                None,
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO skill_provenance
                (skill_name, source, drift, immutable_fields, last_deploy_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("crm-ops", "managed", 1, '["name"]', "legacy", "2026-06-14T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO agent_skills (agent_id, skill_name, enabled, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent.id, "crm-ops", 1, "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")
    _downgrade_to(db, "091")

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        agent_skill_cols = _table_info(conn, "agent_skills")
        state_rows = conn.execute(
            """
            SELECT skill_name, status, global_enabled, audit_verdict, audit_rules, forced
            FROM skill_admin_state
            ORDER BY skill_name
            """
        ).fetchall()
        provenance_rows = conn.execute(
            """
            SELECT skill_name, source, drift, immutable_fields, last_deploy_at
            FROM skill_provenance
            ORDER BY skill_name
            """
        ).fetchall()
    finally:
        conn.close()

    assert "skills" not in tables
    assert "skill_admin_state" in tables
    assert "skill_provenance" in tables
    assert "base_version" not in agent_skill_cols
    assert "drift" not in agent_skill_cols
    assert "drift_at" not in agent_skill_cols
    assert state_rows == [("crm-ops", "quarantined", 0, "rejected", '["rule"]', 1)]
    assert provenance_rows == [("crm-ops", "managed", 0, '["name"]', None)]
