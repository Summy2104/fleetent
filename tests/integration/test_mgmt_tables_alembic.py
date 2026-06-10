"""Integration tests: 4 management tables onboarded into alembic (migration 067).

Covers:
- upgrade head creates api_keys / audit_log / im_connectors / im_channel_allowlist
- columns match the original _init_db DDL exactly
- upgrade on a db that already has these tables is no-op (no data loss)
- fresh upgrade → downgrade → upgrade roundtrip
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


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


def test_upgrade_creates_im_connectors(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "im_connectors" in _tables(db)
    assert _cols(db, "im_connectors") == {
        "id",
        "owner_id",
        "platform",
        "enabled",
        "allowlist_enforced",
        "config",
        "status",
        "last_heartbeat_at",
        "last_error",
        "created_at",
        "updated_at",
    }


def test_upgrade_creates_im_channel_allowlist(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "im_channel_allowlist" in _tables(db)
    assert _cols(db, "im_channel_allowlist") == {
        "id",
        "owner_id",
        "platform",
        "scope_type",
        "scope_id",
        "allowed",
        "note",
        "created_at",
    }


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


def test_upgrade_noop_on_existing_im_connectors(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_connectors (
                id                 INTEGER PRIMARY KEY,
                owner_id           TEXT NOT NULL,
                platform           TEXT NOT NULL,
                enabled            INTEGER NOT NULL DEFAULT 0,
                allowlist_enforced INTEGER NOT NULL DEFAULT 0,
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
            "INSERT INTO im_connectors"
            " (owner_id, platform, enabled, allowlist_enforced, status, created_at, updated_at)"
            " VALUES ('owner1', 'slack', 1, 0, 'connected',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM im_connectors").fetchone()[0]
    assert count == 1


def test_upgrade_noop_on_existing_im_channel_allowlist(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_channel_allowlist (
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
            "INSERT INTO im_channel_allowlist"
            " (owner_id, platform, scope_type, scope_id, allowed, created_at)"
            " VALUES ('owner1', 'slack', 'channel', 'C123', 1, '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM im_channel_allowlist").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# 2.3 roundtrip: upgrade → downgrade → upgrade on fresh db
# ---------------------------------------------------------------------------


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    tables_after_upgrade = _tables(db)
    assert "api_keys" in tables_after_upgrade
    assert "audit_log" in tables_after_upgrade
    assert "im_connectors" in tables_after_upgrade
    assert "im_channel_allowlist" in tables_after_upgrade

    _downgrade(db)
    tables_after_downgrade = _tables(db)
    assert "api_keys" not in tables_after_downgrade
    assert "audit_log" not in tables_after_downgrade
    assert "im_connectors" not in tables_after_downgrade
    assert "im_channel_allowlist" not in tables_after_downgrade

    _apply(db)
    tables_after_reupgrade = _tables(db)
    assert "api_keys" in tables_after_reupgrade
    assert "audit_log" in tables_after_reupgrade
    assert "im_connectors" in tables_after_reupgrade
    assert "im_channel_allowlist" in tables_after_reupgrade
