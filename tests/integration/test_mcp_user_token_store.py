"""Integration: platform-side per-user MCP OAuth token + pending-auth stores (slice 2).

Schema by Alembic against a tmp_path management DB (DATABASE_URL env). Encrypted token
columns, triple-keyed isolation, one-time short-TTL pending-auth. No raw sqlite3 / ORM.
"""

from __future__ import annotations

import pytest

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from cryptography.fernet import Fernet

    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    return db_path


def test_migration_creates_mcp_user_tokens_and_pending_tables(db):
    import sqlite3

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "mcp_user_tokens" in tables
    assert "mcp_oauth_pending" in tables


def test_token_store_roundtrips_and_isolates_by_triple(db):
    from fleetent.platform.connector_management import mcp_user_token_store as store

    store.put_token(
        "u1", "a1", "s1", access_token="AT1", refresh_token="RT1", expires_at=111.0, scope="r"
    )
    store.put_token(
        "u1", "a2", "s1", access_token="AT2", refresh_token=None, expires_at=None, scope=None
    )

    got = store.get_token("u1", "a1", "s1")
    assert got is not None
    assert got.access_token == "AT1"
    assert got.refresh_token == "RT1"
    assert got.expires_at == 111.0
    assert got.scope == "r"
    # Different agent in the triple -> isolated record
    other = store.get_token("u1", "a2", "s1")
    assert other is not None and other.access_token == "AT2" and other.refresh_token is None
    # Untouched triple -> None
    assert store.get_token("u2", "a1", "s1") is None

    store.delete_token("u1", "a1", "s1")
    assert store.get_token("u1", "a1", "s1") is None


def test_token_columns_are_ciphertext_not_plaintext(db):
    import sqlite3

    from fleetent.platform.connector_management import mcp_user_token_store as store

    store.put_token(
        "u9",
        "a9",
        "s9",
        access_token="SECRET-ACCESS",
        refresh_token="SECRET-REFRESH",
        expires_at=1.0,
        scope=None,
    )
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT access_token_ciphertext, refresh_token_ciphertext FROM mcp_user_tokens WHERE user_id='u9'"
    ).fetchone()
    conn.close()
    assert "SECRET-ACCESS" not in row[0]
    assert "SECRET-REFRESH" not in (row[1] or "")


def test_pending_auth_one_time_and_ttl(db):
    from fleetent.platform.connector_management import mcp_user_token_store as store

    clock = {"t": 1000.0}
    store.put_pending(
        state="st-1",
        code_verifier="verifier-xyz",
        user_id="u1",
        agent_id="a1",
        server_id="s1",
        token_url="https://auth/token",
        client_id="cid",
        client_secret_env="CS_ENV",
        redirect_uri="https://platform/oauth/callback",
        now=clock["t"],
    )
    # First consume within TTL succeeds and returns the bound context
    p = store.consume_pending("st-1", now=clock["t"] + 5.0)
    assert p is not None
    assert p.code_verifier == "verifier-xyz"
    assert (p.user_id, p.agent_id, p.server_id) == ("u1", "a1", "s1")
    assert p.token_url == "https://auth/token"
    assert p.client_id == "cid"
    assert p.client_secret_env == "CS_ENV"
    assert p.redirect_uri == "https://platform/oauth/callback"
    # Second consume is rejected (one-time)
    assert store.consume_pending("st-1", now=clock["t"] + 6.0) is None


def test_pending_auth_expired_is_rejected(db):
    from fleetent.platform.connector_management import mcp_user_token_store as store

    store.put_pending(
        state="st-2",
        code_verifier="v",
        user_id="u",
        agent_id="a",
        server_id="s",
        token_url="https://auth/token",
        client_id="cid",
        client_secret_env="",
        redirect_uri="https://platform/oauth/callback",
        now=1000.0,
    )
    # Past TTL -> rejected
    assert store.consume_pending("st-2", now=1000.0 + store.PENDING_TTL_SECONDS + 1.0) is None
