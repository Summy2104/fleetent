"""Integration test: migration 080 — backfill api_keys from users.api_key then drop column.

Verifies upgrade path:
  - Old DB with users.api_key (plaintext, NULL, or empty) runs migrations to head.
  - After migration: users has no api_key column, api_keys has hashed rows for each
    non-NULL/non-empty plaintext, original plaintext key still authenticates.
  - Migration is idempotent (running upgrade on already-migrated DB is a no-op).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _run_migrations(db_path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _make_pre_080_db(db_path) -> None:
    """Build a DB with the old schema (users has api_key column, api_keys table present)."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE alembic_version (
            version_num VARCHAR(32) NOT NULL,
            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
        );
        INSERT INTO alembic_version VALUES ('079');

        CREATE TABLE tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            approver_user_id TEXT,
            created_at TEXT NOT NULL
        );
        INSERT INTO tenants (id, name, created_at) VALUES ('default', 'Default', '2026-01-01');

        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            email TEXT,
            password_hash TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            status TEXT NOT NULL DEFAULT 'active',
            must_reset INTEGER NOT NULL DEFAULT 0,
            tenant_id TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT,
            scope TEXT,
            note TEXT,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            last_ip TEXT,
            last_ua TEXT,
            call_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            approver_user_id TEXT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def test_upgrade_backfills_hashes_and_drops_api_key_column(tmp_path, monkeypatch):
    db = tmp_path / "mgmt.db"
    _make_pre_080_db(db)

    # Insert legacy rows: one active key, one NULL key, one empty-string key
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at) VALUES (?,?,?,?)",
        ("u1", "Alice", "ma-" + "a" * 64, "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at) VALUES (?,?,?,?)",
        ("u2", "Bob", None, "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at) VALUES (?,?,?,?)",
        ("u3", "Carol", "", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    # Assert: users has no api_key column
    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as c:
        inspector = sa.inspect(engine)
        col_names = {col["name"] for col in inspector.get_columns("users")}
        assert "api_key" not in col_names, f"api_key column still present: {col_names}"

        # Assert: api_keys has exactly one row for Alice (non-NULL, non-empty)
        rows = c.execute(sa.text("SELECT user_id, key_hash, scope FROM api_keys")).fetchall()
        alice_rows = [r for r in rows if r[0] == "u1"]
        assert len(alice_rows) == 1
        expected_hash = _hash("ma-" + "a" * 64)
        assert alice_rows[0][1] == expected_hash
        assert json.loads(alice_rows[0][2]) == ["*"]

        # No rows for Bob (NULL) or Carol (empty)
        assert not any(r[0] == "u2" for r in rows)
        assert not any(r[0] == "u3" for r in rows)

    engine.dispose()

    # Assert: original key still authenticates via user_store.authenticate
    import importlib

    import fleetent.user_store as us_mod

    importlib.reload(us_mod)

    result = us_mod.authenticate("ma-" + "a" * 64)
    assert result is not None, "original plaintext key should authenticate after migration"
    user, meta = result
    assert user.id == "u1"
    assert meta["scope"] == ["*"]

    # Bob's NULL → no key → authenticate returns None
    assert us_mod.authenticate("ma-" + "b" * 64) is None


def test_upgrade_is_idempotent(tmp_path, monkeypatch):
    """Running migration 080 on an already-migrated DB is a no-op, no errors."""
    db = tmp_path / "mgmt.db"
    _make_pre_080_db(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    # Run once (builds from 079 base — migration 080 will run)
    _run_migrations(db)
    # Run again — must not raise
    _run_migrations(db)
