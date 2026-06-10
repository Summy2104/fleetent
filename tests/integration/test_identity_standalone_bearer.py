"""Integration test: standalone bearer resolves without platform tables (task 2.1).

Verifies LocalBearerAdapter works in an isolated DB that has only the users table,
simulating a standalone agent environment where platform tables do not exist.
"""

from __future__ import annotations

import sqlite3


def test_standalone_bearer_resolves_without_platform_tables(tmp_path, monkeypatch):
    db = tmp_path / "fleetent.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE users (
            id TEXT PRIMARY KEY, name TEXT, api_key TEXT,
            created_at TEXT, email TEXT, role TEXT DEFAULT 'viewer',
            status TEXT DEFAULT 'active', must_reset INTEGER DEFAULT 0,
            password_hash TEXT, tenant_id TEXT DEFAULT 'default'
        )"""
    )
    api_key = "ma-" + "a" * 64
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at, tenant_id) VALUES (?,?,?,?,?)",
        ("user-1", "Alice", api_key, "2026-01-01", "default"),
    )
    conn.commit()
    conn.close()

    import fleetent.user_store as us

    monkeypatch.setattr(us, "DB_PATH", db)

    from fleetent.identity import LocalBearerAdapter, Principal

    result = LocalBearerAdapter()(api_key)
    assert result == Principal(user_id="user-1", tenant_id="default")


def test_standalone_bearer_blocked_user_rejected(tmp_path, monkeypatch):
    db = tmp_path / "fleetent.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE users (
            id TEXT PRIMARY KEY, name TEXT, api_key TEXT,
            created_at TEXT, email TEXT, role TEXT DEFAULT 'viewer',
            status TEXT DEFAULT 'active', must_reset INTEGER DEFAULT 0,
            password_hash TEXT, tenant_id TEXT DEFAULT 'default'
        )"""
    )
    api_key = "ma-" + "b" * 64
    conn.execute(
        "INSERT INTO users (id, name, api_key, created_at, tenant_id, status) VALUES (?,?,?,?,?,?)",
        ("user-2", "Bob", api_key, "2026-01-01", "default", "blocked"),
    )
    conn.commit()
    conn.close()

    import fleetent.user_store as us

    monkeypatch.setattr(us, "DB_PATH", db)

    from fleetent.identity import LocalBearerAdapter

    assert LocalBearerAdapter()(api_key) is None
