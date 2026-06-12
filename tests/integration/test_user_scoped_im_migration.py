"""Alembic owns the current owner-keyed IM users table shape."""

import sqlite3
from pathlib import Path

from tests.integration._migration_template import apply_migrations


def _cols(db: Path, table: str) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_alembic_creates_owner_keyed_im_users_table(tmp_path: Path) -> None:
    db = tmp_path / "users.db"
    apply_migrations(db)

    assert _cols(db, "im_users") >= {
        "id",
        "owner_id",
        "platform",
        "platform_user_id",
        "user_id",
        "allowed",
        "created_at",
        "meta_json",
    }

    with sqlite3.connect(db) as conn:
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(im_users)")
            if row[2]  # unique only
        }
        assert indexes
