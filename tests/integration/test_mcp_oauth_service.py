"""Integration: platform-side managed OAuth service (callback exchange + refresh).

Drives the real D6 protocol logic against a fake token endpoint (httpx.MockTransport) over
a tmp_path management DB. Verifies token storage, transparent refresh, and that the
refresh_token never surfaces from fetch_access_token.
"""

from __future__ import annotations

import httpx
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


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_complete_callback_exchanges_and_stores_token(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "AT-fresh",
                "refresh_token": "RT-1",
                "expires_in": 3600,
                "scope": "mcp.read",
                "token_type": "Bearer",
            },
        )

    svc.register_pending(
        state="st-abc",
        code_verifier="verifier",
        user_id="u1",
        agent_id="7",
        server_id="crm",
        token_url="https://auth.internal/token",
        client_id="fleetent-crm",
        client_secret_env="",  # PKCE public client, no secret
        redirect_uri="https://platform/oauth/callback",
        now=1000.0,
    )

    async with _mock_client(handler) as client:
        outcome = await svc.complete_callback(
            "the-code", "st-abc", http_client=client, now=lambda: 1001.0
        )

    assert outcome.ok, outcome.detail
    stored = store.get_token("u1", "7", "crm")
    assert stored is not None
    assert stored.access_token == "AT-fresh"
    assert stored.refresh_token == "RT-1"
    assert stored.token_url == "https://auth.internal/token"


async def test_complete_callback_rejects_unknown_state(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    async with _mock_client(lambda r: httpx.Response(200, json={})) as client:
        outcome = await svc.complete_callback(
            "code", "no-such-state", http_client=client, now=lambda: 5.0
        )
    assert not outcome.ok
    assert outcome.status == "invalid_state"


async def test_fetch_access_token_returns_stored_without_refresh_field(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    store.put_token(
        "u1",
        "7",
        "crm",
        access_token="AT-valid",
        refresh_token="RT-1",
        expires_at=10_000.0,
        scope="mcp.read",
        token_url="https://auth.internal/token",
        client_id="c",
        client_secret_env="",
    )
    # Far from expiry -> returned as-is, no network call.
    token = await svc.fetch_access_token("u1", "7", "crm", now=lambda: 1000.0)
    assert token == "AT-valid"  # a bare access token string, never the refresh_token


async def test_fetch_access_token_refreshes_when_expired(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc
    from fleetent.platform.connector_management import mcp_user_token_store as store

    store.put_token(
        "u1",
        "7",
        "crm",
        access_token="AT-old",
        refresh_token="RT-1",
        expires_at=1000.0,
        scope="mcp.read",
        token_url="https://auth.internal/token",
        client_id="c",
        client_secret_env="",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "AT-rotated", "refresh_token": "RT-2", "expires_in": 3600},
        )

    async with _mock_client(handler) as client:
        # now well past expiry -> transparent refresh
        token = await svc.fetch_access_token(
            "u1", "7", "crm", http_client=client, now=lambda: 2000.0
        )

    assert token == "AT-rotated"
    rotated = store.get_token("u1", "7", "crm")
    assert rotated is not None and rotated.refresh_token == "RT-2"


async def test_fetch_access_token_none_when_no_token(db):
    from fleetent.platform.connector_management import mcp_oauth_service as svc

    assert await svc.fetch_access_token("nobody", "7", "crm", now=lambda: 1.0) is None
