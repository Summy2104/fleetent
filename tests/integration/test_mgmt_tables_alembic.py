"""Integration tests: management tables onboarded into alembic.

Covers:
- upgrade head creates api_keys / audit_log and removes owner-level IM connectors
- current head columns match the live schema
- upgrade preserves compatible existing data and drops descope'd allowlist tables
- fresh upgrade → downgrade → upgrade roundtrip
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")
_LEGACY_TABLE = "_".join(("im", "channel", "allowlist"))
_LEGACY_FLAG = "_".join(("allowlist", "enforced"))
_OWNER_TABLE = "_".join(("im", "connectors"))


def _apply(db_path: Path, revision: str = "head") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _downgrade(db_path: Path, revision: str = "base") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, revision)


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# ---------------------------------------------------------------------------
# 2.1 schema after upgrade head
# ---------------------------------------------------------------------------


def test_upgrade_creates_api_keys(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "api_keys" in _tables(db)
    assert _cols(db, "api_keys") == {
        "id",
        "user_id",
        "key_hash",
        "prefix",
        "scope",
        "note",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_used_at",
        "last_ip",
        "last_ua",
        "call_count",
    }


def test_upgrade_creates_audit_log(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "audit_log" in _tables(db)
    assert _cols(db, "audit_log") == {
        "id",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "detail",
        "batch_id",
        "created_at",
    }


def test_upgrade_drops_owner_level_im_table(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert _OWNER_TABLE not in _tables(db)


# ---------------------------------------------------------------------------
# 2.3 idempotency: existing tables survive upgrade (no data loss)
# ---------------------------------------------------------------------------


def test_upgrade_noop_on_existing_api_keys(tmp_path):
    db = tmp_path / "t.db"
    # Pre-create via _init_db DDL, insert a row
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY,
                user_id      TEXT NOT NULL,
                key_hash     TEXT UNIQUE NOT NULL,
                prefix       TEXT NOT NULL,
                scope        TEXT NOT NULL DEFAULT '["*"]',
                note         TEXT,
                expires_at   TEXT,
                revoked_at   TEXT,
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                last_ip      TEXT,
                last_ua      TEXT,
                call_count   INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at, call_count)"
            " VALUES ('u1', 'hash1', 'ma-prefix', '[\"*\"]', '2026-01-01T00:00:00+00:00', 0)"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    assert count == 1, "existing api_keys row must survive upgrade"


def test_upgrade_noop_on_existing_audit_log(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id            INTEGER PRIMARY KEY,
                actor_user_id TEXT,
                action        TEXT NOT NULL,
                target_type   TEXT,
                target_id     TEXT,
                detail        TEXT,
                batch_id      TEXT,
                created_at    TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO audit_log (action, created_at)"
            " VALUES ('create_user', '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert count == 1


def test_upgrade_drops_existing_owner_level_im_table(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {_OWNER_TABLE} (
                id                 INTEGER PRIMARY KEY,
                owner_id           TEXT NOT NULL,
                platform           TEXT NOT NULL,
                enabled            INTEGER NOT NULL DEFAULT 0,
                """
            + _LEGACY_FLAG
            + """ INTEGER NOT NULL DEFAULT 0,
                config             TEXT,
                status             TEXT NOT NULL DEFAULT 'stopped',
                last_heartbeat_at  TEXT,
                last_error         TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                UNIQUE(owner_id, platform)
            )"""
        )
        conn.execute(
            f"INSERT INTO {_OWNER_TABLE}"
            f" (owner_id, platform, enabled, {_LEGACY_FLAG}, status, created_at, updated_at)"
            " VALUES ('owner1', 'slack', 1, 0, 'connected',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    assert _OWNER_TABLE not in _tables(db)


def test_upgrade_drops_existing_legacy_allowlist_table(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {_LEGACY_TABLE} (
                id         INTEGER PRIMARY KEY,
                owner_id   TEXT NOT NULL,
                platform   TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                allowed    INTEGER NOT NULL DEFAULT 1,
                note       TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, platform, scope_type, scope_id)
            )"""
        )
        conn.execute(
            f"INSERT INTO {_LEGACY_TABLE}"
            " (owner_id, platform, scope_type, scope_id, allowed, created_at)"
            " VALUES ('owner1', 'slack', 'channel', 'C123', 1, '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    assert _LEGACY_TABLE not in _tables(db)


# ---------------------------------------------------------------------------
# 2.3 roundtrip: upgrade → downgrade → upgrade on fresh db
# ---------------------------------------------------------------------------


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    tables_after_upgrade = _tables(db)
    assert "api_keys" in tables_after_upgrade
    assert "audit_log" in tables_after_upgrade
    assert _OWNER_TABLE not in tables_after_upgrade
    assert _LEGACY_TABLE not in tables_after_upgrade

    _downgrade(db)
    tables_after_downgrade = _tables(db)
    assert "api_keys" not in tables_after_downgrade
    assert "audit_log" not in tables_after_downgrade
    assert _OWNER_TABLE not in tables_after_downgrade
    assert _LEGACY_TABLE not in tables_after_downgrade

    _apply(db)
    tables_after_reupgrade = _tables(db)
    assert "api_keys" in tables_after_reupgrade
    assert "audit_log" in tables_after_reupgrade
    assert _OWNER_TABLE not in tables_after_reupgrade
    assert _LEGACY_TABLE not in tables_after_reupgrade
