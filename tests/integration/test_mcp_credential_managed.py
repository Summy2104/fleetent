"""Integration: managed per-user MCP api-key credential submission (slice apikey Group 4).

Schema by Alembic against a tmp_path management DB. The agent registers a one-shot pending
(state→triple) through the node loopback (reusing the OAuth pending store); the platform's
``complete_credential_submit`` consumes it and stores the user-supplied key as a *static*
credential — encrypted, OAuth columns empty, never refreshed. Identity comes only from the
state; an invalid / expired / used state is rejected with no write; the plaintext key never
leaves the platform store boundary in the clear.
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


def _register_pending(state: str = "cred-st-1") -> None:
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    # The agent's managed state store posts this through the node loopback when it builds the
    # credential link; OAuth-specific fields are empty for an api-key submission.
    svc.register_pending(
        state=state,
        code_verifier="",
        user_id="uA",
        agent_id="ag1",
        server_id="acme",
        token_url="",
        client_id="",
        client_secret_env="",
        redirect_uri="https://platform/mcp/credential",
        now=1000.0,
    )


def test_valid_submit_stores_static_credential(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    _register_pending("cred-st-1")
    outcome = svc.complete_credential_submit("cred-st-1", "my-api-key", now=1005.0)
    assert outcome.ok and outcome.status == "ok"

    tok = store.get_token("uA", "ag1", "acme")
    assert tok is not None
    assert tok.access_token == "my-api-key"
    assert tok.credential_kind == "static"


async def test_static_credential_is_served_back_unrefreshed(db):
    # The node fetches the key through the same fetch_access_token path as OAuth; a static
    # credential is returned as-is with no refresh attempt (no http client needed).
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    _register_pending("cred-st-2")
    svc.complete_credential_submit("cred-st-2", "k-served", now=1005.0)
    token = await svc.fetch_access_token("uA", "ag1", "acme", now=lambda: 9_999_999.0)
    assert token == "k-served"


def test_unknown_state_rejected_no_write(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    outcome = svc.complete_credential_submit("bogus", "k", now=1005.0)
    assert not outcome.ok and outcome.status == "invalid_state"
    assert store.get_token("uA", "ag1", "acme") is None


def test_expired_state_rejected(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    _register_pending("cred-st-3")
    expired = 1000.0 + store.PENDING_TTL_SECONDS + 1.0
    outcome = svc.complete_credential_submit("cred-st-3", "k", now=expired)
    assert not outcome.ok and outcome.status == "invalid_state"


def test_consumed_state_rejected_second_time(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    _register_pending("cred-st-4")
    assert svc.complete_credential_submit("cred-st-4", "k1", now=1005.0).ok
    second = svc.complete_credential_submit("cred-st-4", "k2", now=1006.0)
    assert not second.ok and second.status == "invalid_state"


def test_missing_key_rejected_and_state_not_consumed(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    _register_pending("cred-st-5")
    bad = svc.complete_credential_submit("cred-st-5", "", now=1005.0)
    assert not bad.ok and bad.status == "invalid_request"
    # state untouched → a later proper submit still works
    assert svc.complete_credential_submit("cred-st-5", "k", now=1006.0).ok


def test_stored_key_is_ciphertext_not_plaintext(db):
    import sqlite3

    from fleetent.platform.connector_management import mcp_oauth_service as svc

    _register_pending("cred-st-6")
    svc.complete_credential_submit("cred-st-6", "PLAINTEXT-SECRET", now=1005.0)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT access_token_ciphertext FROM mcp_user_tokens WHERE server_id='acme'"
    ).fetchone()
    conn.close()
    assert "PLAINTEXT-SECRET" not in row[0]
