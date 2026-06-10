"""Migration contract: quotas and quota_usage tables must not exist in head schema.

Corresponds to descope-quota change: these tables were created by governance/quota._init_db
at runtime (never in alembic), so a fresh alembic head may already lack them — but any
deployed instance may have them from prior runtime _init_db calls. The migration drops them
idempotently (DROP TABLE IF EXISTS). Assertion: head schema does NOT contain them.
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")

_QUOTA_TABLES = {"quotas", "quota_usage"}


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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


def _create_quota_tables(db_path: Path) -> None:
    """Manually create the quota tables as quota._init_db would have, simulating a deployed DB."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quotas (
                scope       TEXT PRIMARY KEY,
                token_limit INTEGER,
                call_limit  INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_usage (
                scope       TEXT PRIMARY KEY,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                calls_used  INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def test_head_schema_does_not_contain_quota_tables(tmp_path):
    """After upgrade head, quota tables MUST NOT exist."""
    db = tmp_path / "test.db"
    _upgrade(db)
    tables = _tables(db)
    assert not (_QUOTA_TABLES & tables), (
        f"quota tables still present in head schema: {_QUOTA_TABLES & tables}"
    )


def test_head_schema_drops_pre_existing_quota_tables(tmp_path):
    """Upgrade head on a DB that already has quota tables (from prior _init_db) drops them."""
    db = tmp_path / "deployed.db"
    # Simulate a deployed instance at revision 063 (before the cleanup migration)
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "063")
    _create_quota_tables(db)  # simulate the runtime _init_db that was called in production
    # Now upgrade to head (064) — DROP TABLE IF EXISTS should clean them up
    _upgrade(db)
    tables = _tables(db)
    assert not (_QUOTA_TABLES & tables), (
        f"quota tables not cleaned up on existing DB: {_QUOTA_TABLES & tables}"
    )


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    """upgrade head → downgrade -1 (restores tables) → upgrade head (drops again)."""
    db = tmp_path / "roundtrip.db"
    _upgrade(db)
    _downgrade(db, "-1")
    _upgrade(db)
    tables = _tables(db)
    assert not (_QUOTA_TABLES & tables), (
        f"quota tables present after roundtrip: {_QUOTA_TABLES & tables}"
    )


def test_downgrade_restores_quota_tables(tmp_path):
    """Downgrading below the drop migration (065) MUST recreate the quota tables."""
    db = tmp_path / "downgrade.db"
    _upgrade(db)
    _downgrade(db, "064")
    tables = _tables(db)
    assert tables >= _QUOTA_TABLES, (
        f"downgrade did not restore quota tables; missing: {_QUOTA_TABLES - tables}"
    )
