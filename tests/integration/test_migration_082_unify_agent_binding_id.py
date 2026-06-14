"""Integration tests for migration 082: unify agent binding ids to INTEGER FKs."""

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


def test_head_schema_unifies_agent_binding_ids_to_integer_foreign_keys(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)

    conn = sqlite3.connect(db)
    try:
        agent_kbs = _table_info(conn, "agent_kbs")
        agent_skills = _table_info(conn, "agent_skills")
        agent_kbs_fks = _fk_rows(conn, "agent_kbs")
        agent_skills_fks = _fk_rows(conn, "agent_skills")
    finally:
        conn.close()

    assert agent_kbs["agent_id"] == ("INTEGER", 3)
    assert agent_skills["agent_id"] == ("INTEGER", 1)
    assert ("tenant_id", ("TEXT", 1)) == ("tenant_id", agent_kbs["tenant_id"])
    assert ("kb_id", ("TEXT", 2)) == ("kb_id", agent_kbs["kb_id"])
    assert agent_skills["skill_name"] == ("TEXT", 2)

    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in agent_kbs_fks
    )
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in agent_skills_fks
    )


def test_upgrade_migrates_numeric_and_name_keyed_agent_bindings(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "081")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    support = agent_store.create_agent("support", "Support.", ["shell"])
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO agent_kbs (tenant_id, kb_id, agent_id, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("default", "kb-numeric", str(support.id), "2026-06-13T00:00:00+00:00", "seed"),
        )
        conn.execute(
            """
            INSERT INTO agent_skills (agent_id, skill_name, enabled, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """,
            (
                str(support.id),
                "crm-ops",
                1,
                "2026-06-13T00:00:00+00:00",
                "seed",
                ops.name,
                "billing",
                1,
                "2026-06-13T00:00:00+00:00",
                "seed",
                "ghost-name",
                "dropped",
                1,
                "2026-06-13T00:00:00+00:00",
                "seed",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        kb_rows = conn.execute(
            "SELECT tenant_id, kb_id, agent_id FROM agent_kbs ORDER BY kb_id"
        ).fetchall()
        skill_rows = conn.execute(
            "SELECT agent_id, skill_name, enabled FROM agent_skills ORDER BY skill_name"
        ).fetchall()
    finally:
        conn.close()

    assert kb_rows == [("default", "kb-numeric", support.id)]
    assert skill_rows == [
        (ops.id, "billing", 1),
        (support.id, "crm-ops", 1),
    ]
