"""Integration: user_store uses db.py boundary (WAL + named params).

Task 2.1 / 2.2 (retire-raw-sqlite-connect):
- Verifies create/get_by_id/get_by_email/list/update/authenticate all work.
- Verifies the SQLite connection opens in WAL journal mode.
Uses DATABASE_URL monkeypatch (not DB_PATH) as the isolation mechanism.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    from tests.integration._migration_template import apply_migrations

    p = tmp_path / "management.db"
    apply_migrations(p)
    return p


@pytest.fixture(autouse=True)
def _use_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


# ── WAL mode ──────────────────────────────────────────────────────────────────


def test_user_store_connection_uses_wal(db_path: Path) -> None:
    """user_store must open connections with WAL journal mode via db.py."""
    from fleetent import user_store

    user_store.create_user("WalCheck")  # opens a connection internally
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal", f"Expected WAL, got {mode!r}"


# ── CRUD behaviour ────────────────────────────────────────────────────────────


def test_create_user_returns_user() -> None:
    from fleetent import user_store

    user, api_key = user_store.create_user("Alice")
    assert user.name == "Alice"
    assert api_key.startswith("ma-")
    assert len(user.id) == 36


def test_get_by_id_found() -> None:
    from fleetent import user_store

    user, _ = user_store.create_user("Bob")
    found = user_store.get_by_id(user.id)
    assert found is not None
    assert found.name == "Bob"


def test_get_by_id_not_found() -> None:
    from fleetent import user_store

    assert user_store.get_by_id("00000000-0000-0000-0000-000000000000") is None


def test_get_by_email_found() -> None:
    from fleetent import user_store

    user, _ = user_store.create_user("Carol", email="carol@example.com")
    found = user_store.get_by_email("default", "carol@example.com")
    assert found is not None
    assert found.id == user.id


def test_get_by_email_not_found() -> None:
    from fleetent import user_store

    assert user_store.get_by_email("default", "nobody@example.com") is None


def test_list_users_returns_all() -> None:
    from fleetent import user_store

    user_store.create_user("Dave")
    user_store.create_user("Eve")
    users = user_store.list_users()
    names = {u.name for u in users}
    assert {"Dave", "Eve"} <= names


def test_rotate_key_changes_api_key() -> None:
    from fleetent import user_store

    user, old_key = user_store.create_user("Frank")
    updated, new_key = user_store.rotate_key(user.id)
    assert new_key != old_key
    assert new_key.startswith("ma-")
    assert user_store.get_by_api_key(old_key) is None
    assert user_store.get_by_api_key(new_key) is not None


def test_authenticate_legacy_key() -> None:
    from fleetent import user_store

    user, api_key = user_store.create_user("Grace")
    result = user_store.authenticate(api_key)
    assert result is not None
    found_user, meta = result
    assert found_user.id == user.id


def test_authenticate_invalid_key_returns_none() -> None:
    from fleetent import user_store

    assert user_store.authenticate("ma-" + "x" * 64) is None


def test_update_via_set_role() -> None:
    from fleetent import user_store

    user, _ = user_store.create_user("Harry")
    user_store.set_role(user.id, "admin")
    updated = user_store.get_by_id(user.id)
    assert updated is not None
    assert updated.role == "admin"
