"""Integration tests for migration 095: backflow fidelity fixes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


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


def test_head_schema_adds_base_commit_and_bundle_storage(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        agent_skills = _table_info(conn, "agent_skills")
        proposals = _table_info(conn, "backflow_proposals")
    finally:
        conn.close()

    assert agent_skills["base_commit"] == ("TEXT", 0, None)
    assert proposals["base_commit"] == ("TEXT", 0, None)
    assert proposals["proposed_bundle"] == ("TEXT", 0, None)
    assert "proposed_content" not in proposals


def test_upgrade_migrates_legacy_proposed_content_to_bundle(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "094")

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO backflow_proposals (
                status, agent_id, skill_name, base_version, proposed_content,
                conflict, overridden_head, forked_as, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pending",
                7,
                "crm-ops",
                "a" * 64,
                "---\nname: crm-ops\ndescription: test\n---\nlegacy body",
                0,
                None,
                None,
                "2026-06-15T00:00:00+00:00",
                "2026-06-15T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """
            SELECT skill_name, base_version, base_commit, proposed_bundle
            FROM backflow_proposals
            """
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "crm-ops",
        "a" * 64,
        None,
        json.dumps({"SKILL.md": "---\nname: crm-ops\ndescription: test\n---\nlegacy body"}),
    )


def test_downgrade_restores_legacy_backflow_content_column(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")
    _downgrade_to(db, "094")

    conn = sqlite3.connect(db)
    try:
        proposals = _table_info(conn, "backflow_proposals")
        agent_skills = _table_info(conn, "agent_skills")
    finally:
        conn.close()

    assert "base_commit" not in agent_skills
    assert "base_commit" not in proposals
    assert proposals["proposed_content"] == ("TEXT", 0, None)
    assert "proposed_bundle" not in proposals
