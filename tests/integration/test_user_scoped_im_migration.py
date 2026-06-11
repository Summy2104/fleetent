"""Owner-keyed shape of IM tables after migration.

im_users: owner_id added by identity._init_db() (still self-manages via ensure_schema).
im_connectors / im_channel_allowlist: now created by alembic migration 067 with
owner_id from the start — no runtime rebuild path.
"""

import datetime
import sqlite3

import pytest

from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    return p


def _seed_admin(db: object) -> None:
    # Users table is now Alembic-managed (migration 068); _init_db() is a no-op.
    # Create it directly here because this test exercises the pre-migration IM rebuild
    # path and cannot use apply_migrations (it creates IM tables in legacy format).
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with sqlite3.connect(str(db)) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                email TEXT, password_hash TEXT,
                role TEXT NOT NULL DEFAULT 'viewer',
                status TEXT NOT NULL DEFAULT 'active',
                must_reset INTEGER NOT NULL DEFAULT 0,
                tenant_id TEXT NOT NULL DEFAULT 'default'
            )"""
        )
        c.execute(
            "INSERT INTO users (id, name, api_key, created_at, role)"
            " VALUES ('admin1', 'admin', 'ma-x', ?, 'built_in_admin')",
            (now,),
        )


def _cols(db: object, table: str) -> set[str]:
    with sqlite3.connect(str(db)) as c:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_im_users_rebuilt_owner_keyed(db):
    _seed_admin(db)
    with sqlite3.connect(str(db)) as c:
        c.execute(
            """CREATE TABLE im_users (
                id INTEGER PRIMARY KEY, platform TEXT NOT NULL, platform_user_id TEXT NOT NULL,
                user_id TEXT NOT NULL, allowed BOOLEAN NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE(platform, platform_user_id))"""
        )
        c.execute(
            "INSERT INTO im_users (platform, platform_user_id, user_id, allowed, created_at)"
            " VALUES ('slack', 'U1', 'u1', 1, 't')"
        )

    im_user_store._init_db()

    assert "owner_id" in _cols(db, "im_users")
    with sqlite3.connect(str(db)) as c:
        assert c.execute("SELECT owner_id FROM im_users").fetchone()[0] == "admin1"
        # same platform user under another owner coexists
        c.execute(
            "INSERT INTO im_users"
            " (owner_id, platform, platform_user_id, user_id, allowed, created_at)"
            " VALUES ('owner2', 'slack', 'U1', 'u2', 1, 't')"
        )
        assert c.execute("SELECT COUNT(*) FROM im_users").fetchone()[0] == 2


def test_alembic_creates_owner_keyed_im_tables(tmp_path):
    """Migration 067 creates im_connectors and im_channel_allowlist with owner_id from the start."""
    db = tmp_path / "t.db"
    apply_migrations(db)
    assert "owner_id" in _cols(db, "im_connectors")
    assert "owner_id" in _cols(db, "im_channel_allowlist")
