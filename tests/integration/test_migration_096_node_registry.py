"""Integration tests for the node registry management migration."""

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


def _unique_indexes(conn: sqlite3.Connection, table: str) -> dict[str, list[str]]:
    indexes: dict[str, list[str]] = {}
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if int(row[2]) != 1:
            continue
        index_name = str(row[1])
        columns = [
            str(info[2]) for info in conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        ]
        indexes[index_name] = columns
    return indexes


def test_head_schema_adds_nodes_and_agent_placements(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        node_columns = _table_columns(conn, "nodes")
        node_pk = _pk_columns(conn, "nodes")
        node_unique_indexes = _unique_indexes(conn, "nodes")
        placement_columns = _table_columns(conn, "agent_placements")
        placement_pk = _pk_columns(conn, "agent_placements")
        placement_fks = _foreign_keys(conn, "agent_placements")
    finally:
        conn.close()

    assert "nodes" in tables
    assert "agent_placements" in tables
    assert node_columns == [
        "id",
        "name",
        "key_hash",
        "labels",
        "registered_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    ]
    assert node_pk == ["id"]
    assert ["key_hash"] in node_unique_indexes.values()
    assert placement_columns == [
        "agent_id",
        "node_id",
        "pinned_at",
        "pinned_by",
        "updated_at",
    ]
    assert placement_pk == ["agent_id"]
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in placement_fks
    )
    assert any(
        row[2] == "nodes" and row[3] == "node_id" and row[4] == "id" and row[6] == "RESTRICT"
        for row in placement_fks
    )
