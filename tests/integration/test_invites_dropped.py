"""Migration contract: invites table must not exist in head schema.

The invites table was created at runtime by invite_store._init_db() (never in alembic).
Migration 064 adds an explicit DROP TABLE IF EXISTS so production DBs that ran the
invite_store code are cleaned up on the next upgrade.
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")

_INVITES_DDL = """
    CREATE TABLE invites (
        id         INTEGER PRIMARY KEY,
        email      TEXT NOT NULL,
        token_hash TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used_at    TEXT,
        created_at TEXT NOT NULL
    )
"""


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def _upgrade(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _downgrade(db_path: Path, target: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, target)


def test_head_schema_does_not_contain_invites_table(tmp_path):
    """upgrade head on a DB that had the invite table pre-created → must drop it."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute(_INVITES_DDL)
    conn.commit()
    conn.close()

    _upgrade(db)
    tables = _tables(db)
    assert "invites" not in tables, "invites table still present after upgrade head"


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    """upgrade head → downgrade -1 → upgrade head must complete without error."""
    db = tmp_path / "roundtrip.db"
    _upgrade(db)
    _downgrade(db, "-1")
    _upgrade(db)
    assert "invites" not in _tables(db)


def test_downgrade_restores_invites_table(tmp_path):
    """After downgrade -1 from head, invites table must be restored (downgrade is reversible)."""
    db = tmp_path / "downgrade.db"
    _upgrade(db)
    _downgrade(db, "-1")
    tables = _tables(db)
    assert "invites" in tables, f"downgrade did not restore invites table; present: {tables}"
