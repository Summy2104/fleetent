"""Integration test: standalone bearer resolves via api_keys table (task 2.2).

Verifies LocalBearerAdapter works with a DB that has users + api_keys tables,
simulating a standalone agent environment (no platform tables needed).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _make_minimal_db(path, user_id: str, name: str, api_key: str, status: str = "active") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            created_at TEXT NOT NULL, email TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            status TEXT NOT NULL DEFAULT 'active',
            must_reset INTEGER NOT NULL DEFAULT 0,
            password_hash TEXT, tenant_id TEXT NOT NULL DEFAULT 'default'
        )"""
    )
    conn.execute(
        """CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT '["*"]',
            note TEXT,
            revoked_at TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT,
            last_ip TEXT,
            last_ua TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO users (id, name, created_at, tenant_id, status) VALUES (?,?,?,?,?)",
        (user_id, name, "2026-01-01", "default", status),
    )
    conn.execute(
        "INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at) VALUES (?,?,?,?,?)",
        (user_id, _hash(api_key), api_key[:11], json.dumps(["*"]), "2026-01-01"),
    )
    conn.commit()
    conn.close()


def test_standalone_bearer_resolves_without_platform_tables(tmp_path, monkeypatch):
    db = tmp_path / "fleetent.db"
    api_key = "ma-" + "a" * 64
    _make_minimal_db(db, "user-1", "Alice", api_key)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    from fleetent.identity import LocalBearerAdapter, Principal

    result = LocalBearerAdapter()(api_key)
    assert result == Principal(user_id="user-1", tenant_id="default")


def test_standalone_bearer_blocked_user_rejected(tmp_path, monkeypatch):
    db = tmp_path / "fleetent.db"
    api_key = "ma-" + "b" * 64
    _make_minimal_db(db, "user-2", "Bob", api_key, status="blocked")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    from fleetent.identity import LocalBearerAdapter

    assert LocalBearerAdapter()(api_key) is None
