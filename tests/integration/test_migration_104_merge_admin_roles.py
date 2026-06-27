"""Integration tests for merging built_in_admin into admin."""

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


def test_head_rewrites_builtin_admin_roles_to_admin(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    command.upgrade(_config(db), "103")

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, role, status, tenant_id)
            VALUES
              ('u-bootstrap', 'admin', '2026-06-27T00:00:00+00:00',
               'built_in_admin', 'active', 'default'),
              ('u-extra', 'extra', '2026-06-27T00:00:00+00:00',
               'built_in_admin', 'blocked', 'default'),
              ('u-admin', 'real-admin', '2026-06-27T00:00:00+00:00',
               'admin', 'active', 'default')
            """
        )

    command.upgrade(_config(db), "head")

    with sqlite3.connect(db) as conn:
        role_counts = dict(conn.execute("SELECT role, COUNT(*) FROM users GROUP BY role"))

    assert role_counts["admin"] == 3
    assert "built_in_admin" not in role_counts
