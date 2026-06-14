"""Alembic owns the current IM users table shape."""

import sqlite3
from pathlib import Path

from fleetent import user_store
from tests.integration._migration_template import apply_migrations


def _cols(db: Path, table: str) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _unique_indexes(db: Path, table: str) -> dict[str, tuple[str, ...]]:
    with sqlite3.connect(db) as conn:
        unique_indexes: dict[str, tuple[str, ...]] = {}
        for row in conn.execute(f"PRAGMA index_list({table})"):
            if not row[2]:
                continue
            unique_indexes[row[1]] = tuple(
                col[2] for col in conn.execute(f"PRAGMA index_info({row[1]})") if col[2] is not None
            )
        return unique_indexes


def _foreign_keys(db: Path, table: str) -> list[sqlite3.Row]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_alembic_creates_identity_only_im_users_table(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    assert _cols(db, "im_users") == {
        "id",
        "platform",
        "platform_user_id",
        "user_id",
        "created_at",
        "meta_json",
    }

    assert ("platform", "platform_user_id") in _unique_indexes(db, "im_users").values()

    foreign_keys = _foreign_keys(db, "im_users")
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["table"] == "users"
    assert foreign_keys[0]["from"] == "user_id"
    assert foreign_keys[0]["to"] == "id"
    assert foreign_keys[0]["on_delete"].upper() == "CASCADE"


def test_deleting_user_cascades_im_identity_rows(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    user, _ = user_store.create_user("Alice")

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO im_users (platform, platform_user_id, user_id, created_at, meta_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("slack", "U123", user.id, "2026-06-14T00:00:00+00:00", None),
        )
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) FROM im_users WHERE user_id = ?", (user.id,)
        ).fetchone()[0]
        assert before == 1
        conn.execute("DELETE FROM users WHERE id = ?", (user.id,))
        conn.commit()
        after = conn.execute(
            "SELECT COUNT(*) FROM im_users WHERE user_id = ?", (user.id,)
        ).fetchone()[0]

    assert after == 0
