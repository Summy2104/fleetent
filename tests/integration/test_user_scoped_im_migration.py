"""In-place rebuild of legacy IM tables to owner-keyed shape, backfilling admin owner.

The IM/user subsystem bootstraps schema via each store's idempotent `_init_db()` (not
Alembic). These tests assert the owner_id rebuild preserves rows and backfills the
built-in admin owner, matching the established `allowed`-column precedent.
"""

import datetime
import sqlite3

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import channel_allowlist as im_channel_allowlist
from fleetent.platform.im_gateway_management import connector_store as im_connector_store
from fleetent.platform.im_gateway_management import identity as im_user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    for mod in (user_store, im_user_store, im_connector_store, im_channel_allowlist):
        monkeypatch.setattr(mod, "DB_PATH", p)
    return p


def _seed_admin(db: object) -> None:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    user_store._init_db()
    with sqlite3.connect(str(db)) as c:
        c.execute(
            "INSERT INTO users (id, name, api_key, created_at, role)"
            " VALUES ('admin1', 'admin', 'ma-x', ?, 'built_in_admin')",
            (now,),
        )


def _cols(db: object, table: str) -> set[str]:
    with sqlite3.connect(str(db)) as c:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_connectors_rebuilt_owner_keyed(db):
    _seed_admin(db)
    with sqlite3.connect(str(db)) as c:
        c.execute(
            """CREATE TABLE im_connectors (
                id INTEGER PRIMARY KEY, platform TEXT UNIQUE NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0, allowlist_enforced INTEGER NOT NULL DEFAULT 0,
                config TEXT, status TEXT NOT NULL DEFAULT 'stopped',
                last_heartbeat_at TEXT, last_error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        c.execute(
            "INSERT INTO im_connectors (platform, enabled, status, created_at, updated_at)"
            " VALUES ('slack', 1, 'stopped', 't', 't')"
        )

    im_connector_store._init_db()

    assert "owner_id" in _cols(db, "im_connectors")
    with sqlite3.connect(str(db)) as c:
        row = c.execute("SELECT owner_id, platform, enabled FROM im_connectors").fetchone()
        assert row == ("admin1", "slack", 1)
        # same platform under a different owner now coexists
        c.execute(
            "INSERT INTO im_connectors"
            " (owner_id, platform, enabled, status, created_at, updated_at)"
            " VALUES ('owner2', 'slack', 0, 'stopped', 't', 't')"
        )
        assert c.execute("SELECT COUNT(*) FROM im_connectors").fetchone()[0] == 2


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


def test_channel_allowlist_rebuilt_owner_keyed(db):
    _seed_admin(db)
    with sqlite3.connect(str(db)) as c:
        c.execute(
            """CREATE TABLE im_channel_allowlist (
                id INTEGER PRIMARY KEY, platform TEXT NOT NULL, scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL, allowed INTEGER NOT NULL DEFAULT 1, note TEXT,
                created_at TEXT NOT NULL, UNIQUE(platform, scope_type, scope_id))"""
        )
        c.execute(
            "INSERT INTO im_channel_allowlist (platform, scope_type, scope_id, allowed, created_at)"
            " VALUES ('slack', 'channel', 'C1', 1, 't')"
        )

    im_channel_allowlist._init_db()

    assert "owner_id" in _cols(db, "im_channel_allowlist")
    with sqlite3.connect(str(db)) as c:
        assert c.execute("SELECT owner_id FROM im_channel_allowlist").fetchone()[0] == "admin1"


def test_fresh_db_is_owner_keyed(db):
    _seed_admin(db)
    im_connector_store._init_db()
    im_user_store._init_db()
    im_channel_allowlist._init_db()
    assert "owner_id" in _cols(db, "im_connectors")
    assert "owner_id" in _cols(db, "im_users")
    assert "owner_id" in _cols(db, "im_channel_allowlist")
