"""Integration tests for Group 7: standalone self-hosted OAuth callback + self-refresh.

7.1 GET /oauth/callback (FastAPI TestClient): a valid one-shot ``state`` reverse-resolves
``(user, agent, server)`` + PKCE verifier, exchanges the ``code`` at the (mocked) token
endpoint, and persists the token, encrypted, in the local per-agent token library; the state
is then consumed. An invalid / expired / already-used state is rejected (4xx) with NO token
written and NO exchange. Identity comes only from ``state`` — the callback carries no auth.

7.3 access-token expiry → the wired transparent refresher refreshes via the (mocked) token
endpoint and writes the rotated token back to the local DB, so the next resolve sees it —
transparent to the caller.

The token endpoint is a ``httpx.MockTransport`` (no network); the per-agent ``agent_state.db``
is tmp_path-backed and migrated (never touches ``data/``).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
import fleetent.integrations.mcp.standalone_callback as sc
from fleetent.db import SQLiteDatabase
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import (
    UserToken,
    resolve_user_token,
    set_local_user_token_store,
)
from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore
from fleetent.runtime import agent_app
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("PUO_SECRET", "shh-client-secret")


@pytest.fixture(autouse=True)
def _clean_seams(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    az.reset_oauth_state_store()
    az.set_redirect_base("https://agent.internal")
    yield
    az.reset_oauth_state_store()
    az.set_redirect_base(None)
    mc.set_token_refresher(None)


def _migrated_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _per_user_server(sid: str = "puo") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
        authorization_endpoint="https://as.internal/authorize",
        token_url="https://as.internal/token",
        client_id="client-123",
        client_secret_env="PUO_SECRET",
        scope="read",
        redirect_path="/oauth/callback",
    )


def _mock_token_client(captured: list[dict], *, response: dict, status: int = 200):
    """Build a factory yielding a MockTransport client recording the posted form."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        captured.append(dict(p.split("=", 1) for p in body.split("&")))
        return httpx.Response(status, json=response)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


# ── 7.1 callback ────────────────────────────────────────────────────────────────


def test_callback_valid_state_exchanges_and_stores(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    captured: list[dict] = []
    monkeypatch.setattr(
        sc,
        "create_mcp_http_client",
        _mock_token_client(
            captured,
            response={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "scope": "read",
                "token_type": "Bearer",
            },
        ),
    )

    # Issue a real one-shot state bound to the triple (as link-build would).
    state = az.get_oauth_state_store().issue("uA", "ag1", "puo", "verifier-xyz")

    client = TestClient(agent_app.build_app("ag1"), raise_server_exceptions=True)
    resp = client.get("/oauth/callback", params={"code": "the-code", "state": state})

    assert resp.status_code == 200, resp.text
    # token persisted under the triple from the state
    got = store.get("uA", "ag1", "puo")
    assert got is not None and got.access_token == "AT" and got.refresh_token == "RT"
    # exchange used the bound verifier + the code (client auth via client_secret_post)
    assert captured[0]["code"] == "the-code"
    assert captured[0]["code_verifier"] == "verifier-xyz"
    assert captured[0]["grant_type"] == "authorization_code"
    # state is one-shot: consumed
    assert az.get_oauth_state_store().consume(state) is None


def test_callback_invalid_state_rejected_no_write(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    mc._server_registry[(None, "puo")] = _per_user_server("puo")

    def _boom() -> httpx.AsyncClient:
        raise AssertionError("must not hit the token endpoint on an invalid state")

    monkeypatch.setattr(sc, "create_mcp_http_client", _boom)

    client = TestClient(agent_app.build_app("ag1"), raise_server_exceptions=True)
    resp = client.get("/oauth/callback", params={"code": "x", "state": "never-issued"})

    assert resp.status_code == 400
    assert store.get("uA", "ag1", "puo") is None


def test_callback_consumed_state_rejected(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    mc._server_registry[(None, "puo")] = _per_user_server("puo")
    monkeypatch.setattr(
        sc,
        "create_mcp_http_client",
        _mock_token_client([], response={"access_token": "AT", "token_type": "Bearer"}),
    )

    state = az.get_oauth_state_store().issue("uA", "ag1", "puo", "v")
    client = TestClient(agent_app.build_app("ag1"), raise_server_exceptions=True)
    first = client.get("/oauth/callback", params={"code": "c", "state": state})
    assert first.status_code == 200
    # replay the same state → rejected, no second write
    second = client.get("/oauth/callback", params={"code": "c", "state": state})
    assert second.status_code == 400


def test_callback_missing_code_rejected(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    set_local_user_token_store(StandaloneUserTokenStore(db))
    mc._server_registry[(None, "puo")] = _per_user_server("puo")
    state = az.get_oauth_state_store().issue("uA", "ag1", "puo", "v")
    client = TestClient(agent_app.build_app("ag1"), raise_server_exceptions=True)
    resp = client.get("/oauth/callback", params={"state": state})
    assert resp.status_code == 400


# ── 7.3 transparent self-refresh ─────────────────────────────────────────────────


async def test_refresher_refreshes_and_updates_db(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    # seed an expired token with a refresh token
    store.put("uA", "ag1", "puo", UserToken("OLD", "RT", expires_at=100.0, scope="read"))

    captured: list[dict] = []
    refresher = sc.build_standalone_token_refresher(
        store,
        http_client_factory=_mock_token_client(
            captured,
            response={
                "access_token": "NEW",
                "refresh_token": "RT2",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        ),
        now=lambda: 1000.0,
    )
    mc.set_token_refresher(refresher)

    old = store.get("uA", "ag1", "puo")
    out = await refresher("puo", "uA", "ag1", old)

    assert out is not None and out.access_token == "NEW"
    assert captured[0]["grant_type"] == "refresh_token"
    assert captured[0]["refresh_token"] == "RT"
    # DB now holds the rotated token → the next resolve is transparent to the caller
    assert resolve_user_token("puo", "uA", "ag1").access_token == "NEW"
    assert resolve_user_token("puo", "uA", "ag1").expires_at == 1000.0 + 3600


async def test_refresher_revoked_clears_token(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    mc._server_registry[(None, "puo")] = _per_user_server("puo")
    store.put("uA", "ag1", "puo", UserToken("OLD", "RT", expires_at=100.0, scope="read"))

    captured: list[dict] = []
    refresher = sc.build_standalone_token_refresher(
        store,
        http_client_factory=_mock_token_client(
            captured, response={"error": "invalid_grant"}, status=400
        ),
        now=lambda: 1000.0,
    )

    out = await refresher("puo", "uA", "ag1", store.get("uA", "ag1", "puo"))
    assert out is None  # genuine auth failure → drives re-authorization
    assert resolve_user_token("puo", "uA", "ag1") is None  # bad token cleared


async def test_ensure_fresh_uses_wired_refresher_end_to_end(monkeypatch, tmp_path):
    """The full pre-call gate refreshes via the wired refresher and the store reflects it."""
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    set_local_user_token_store(store)
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    store.put("uA", "ag1", "puo", UserToken("OLD", "RT", expires_at=100.0, scope="read"))

    monkeypatch.setattr(mc.time, "time", lambda: 1000.0)
    sc.wire_standalone_oauth(store)
    # re-point the refresher's clock + mock transport for determinism
    captured: list[dict] = []
    mc.set_token_refresher(
        sc.build_standalone_token_refresher(
            store,
            http_client_factory=_mock_token_client(
                captured,
                response={"access_token": "NEW2", "expires_in": 3600, "token_type": "Bearer"},
            ),
            now=lambda: 1000.0,
        )
    )

    ok = await mc._ensure_fresh_user_token(server, "uA", "ag1")
    assert ok is True
    assert resolve_user_token("puo", "uA", "ag1").access_token == "NEW2"
