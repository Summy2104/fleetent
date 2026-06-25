"""DB-backed standalone per-user MCP token store tests.

The ``mcp_user_tokens`` table is created by the unified AGENT_STATE_MIGRATIONS on the
per-agent agent_state.db (migrate-on-open + PRAGMA user_version gate). Tests inject a
tmp_path-backed migrated handle — never touching ``data/`` — and verify Fernet-encrypted
access/refresh persistence, triple isolation, overwrite, delete, and that ciphertext is
never written in the clear.
"""

from __future__ import annotations

import sqlite3

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))


def _migrated_db(tmp_path, agent_id="default"):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    return router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)


def _store(tmp_path):
    from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore

    return StandaloneUserTokenStore(_migrated_db(tmp_path))


def _token(access="at", refresh="rt", expires_at=999.0, scope="read"):
    from fleetent.integrations.mcp.per_user_tokens import UserToken

    return UserToken(access_token=access, refresh_token=refresh, expires_at=expires_at, scope=scope)


def test_get_missing_returns_none(tmp_path):
    assert _store(tmp_path).get("u1", "a1", "s1") is None


def test_put_then_get_round_trips_all_fields(tmp_path):
    store = _store(tmp_path)
    store.put("u1", "a1", "s1", _token(access="A", refresh="R", expires_at=42.5, scope="x y"))
    got = store.get("u1", "a1", "s1")
    assert got is not None
    assert got.access_token == "A"
    assert got.refresh_token == "R"
    assert got.expires_at == 42.5
    assert got.scope == "x y"


def test_put_allows_null_refresh_and_expiry(tmp_path):
    store = _store(tmp_path)
    store.put("u1", "a1", "s1", _token(refresh=None, expires_at=None, scope=None))
    got = store.get("u1", "a1", "s1")
    assert got.refresh_token is None
    assert got.expires_at is None
    assert got.scope is None


def test_triples_are_isolated(tmp_path):
    store = _store(tmp_path)
    store.put("u1", "a1", "s1", _token(access="for-u1-a1-s1"))
    assert store.get("u2", "a1", "s1") is None
    assert store.get("u1", "a2", "s1") is None
    assert store.get("u1", "a1", "s2") is None
    assert store.get("u1", "a1", "s1").access_token == "for-u1-a1-s1"


def test_put_overwrites_same_triple(tmp_path):
    store = _store(tmp_path)
    store.put("u1", "a1", "s1", _token(access="old"))
    store.put("u1", "a1", "s1", _token(access="new"))
    assert store.get("u1", "a1", "s1").access_token == "new"


def test_delete_only_affects_target_triple(tmp_path):
    store = _store(tmp_path)
    store.put("u1", "a1", "s1", _token())
    store.put("u1", "a1", "s2", _token())
    store.delete("u1", "a1", "s1")
    assert store.get("u1", "a1", "s1") is None
    assert store.get("u1", "a1", "s2") is not None


def test_tokens_are_encrypted_at_rest(tmp_path):
    db = _migrated_db(tmp_path)
    from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore

    store = StandaloneUserTokenStore(db)
    store.put("u1", "a1", "s1", _token(access="PLAINTEXT_ACCESS", refresh="PLAINTEXT_REFRESH"))

    # Read raw ciphertext columns directly — plaintext must never appear on disk.
    conn = sqlite3.connect(db.path)
    try:
        row = conn.execute(
            "SELECT access_token_ciphertext, refresh_token_ciphertext FROM mcp_user_tokens"
        ).fetchone()
    finally:
        conn.close()
    assert "PLAINTEXT_ACCESS" not in row[0]
    assert "PLAINTEXT_REFRESH" not in row[1]


def test_migrate_on_open_is_idempotent(tmp_path):
    store1 = _store(tmp_path)
    store1.put("u1", "a1", "s1", _token(access="kept"))
    # Re-open + migrate must not drop existing data.
    store2 = _store(tmp_path)
    assert store2.get("u1", "a1", "s1").access_token == "kept"


def test_schema_too_new_is_refused(tmp_path):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.schema_migrations import SchemaTooNewError, migrate
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", "default").open_state_db(MIGRATIONS)
    # Stamp a future version → opening with current code must refuse.
    conn = sqlite3.connect(db.path)
    try:
        conn.execute(f"PRAGMA user_version = {MIGRATIONS[-1][0] + 100}")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaTooNewError):
        migrate(db, MIGRATIONS)
