"""Integration tests for the nodes.forward_host migration (102)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _column_info(conn: sqlite3.Connection, table: str) -> dict[str, tuple[object, ...]]:
    return {str(row[1]): row for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_head_adds_nodes_forward_host_nullable(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    command.upgrade(_config(db), "head")

    conn = sqlite3.connect(db)
    try:
        cols = _column_info(conn, "nodes")
    finally:
        conn.close()

    assert "forward_host" in cols
    # PRAGMA table_info column index 3 is the NOT NULL flag; nullable => 0.
    assert int(cols["forward_host"][3]) == 0  # type: ignore[arg-type]


def test_downgrade_removes_forward_host(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    command.upgrade(_config(db), "head")
    command.downgrade(_config(db), "101")

    conn = sqlite3.connect(db)
    try:
        cols = _column_info(conn, "nodes")
    finally:
        conn.close()

    assert "forward_host" not in cols
