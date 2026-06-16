"""Integration tests for the node agent status management migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    ordered = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return [name for _, name in ordered]


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_head_schema_adds_node_agent_status(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        columns = _table_columns(conn, "node_agent_status")
        pk = _pk_columns(conn, "node_agent_status")
        fks = _foreign_keys(conn, "node_agent_status")
    finally:
        conn.close()

    assert "node_agent_status" in tables
    assert columns == [
        "agent_id",
        "node_id",
        "phase",
        "pid",
        "health",
        "detail",
        "reported_at",
    ]
    assert pk == ["agent_id"]
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in fks
    )
    assert any(
        row[2] == "nodes" and row[3] == "node_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in fks
    )
