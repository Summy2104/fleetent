"""Integration: node↔platform per-user OAuth endpoints + public callback (slice 2).

Endpoint wiring/auth/response mapping (the OAuth machinery itself is covered in
test_mcp_oauth_service.py). node endpoints require a valid node service key; the callback
is public (the OAuth provider redirects the user's browser to it).
"""

from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fleetent.platform.connector_management import mcp_oauth_service, mcp_user_token_store
from fleetent.platform.node_management import node_store
from fleetent.server import app
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(db_path)
    return TestClient(app, raise_server_exceptions=True)


def _register_node(node_id: str = "node-a") -> str:
    plaintext, _ = node_store.register_node(node_id, name="Node A")
    return plaintext


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_oauth_pending_endpoint_registers_with_node_auth(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    key = _register_node()

    resp = client.post(
        "/nodes/node-a/mcp/oauth-pending",
        headers=_bearer(key),
        json={
            "state": "st-1",
            "code_verifier": "v",
            "user_id": "u1",
            "agent_id": "7",
            "server_id": "crm",
            "token_url": "https://auth/token",
            "client_id": "cid",
            "client_secret_env": "",
            "redirect_uri": "https://platform/oauth/callback",
        },
    )
    assert resp.status_code == 200
    # The pending row is now consumable (one-time).
    pending = mcp_user_token_store.consume_pending("st-1", now=1.0)
    assert pending is not None and pending.user_id == "u1"


def test_oauth_pending_rejects_non_node(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    _register_node()
    resp = client.post(
        "/nodes/node-a/mcp/oauth-pending",
        headers=_bearer("ma-bogus"),
        json={
            "state": "x",
            "code_verifier": "v",
            "user_id": "u",
            "agent_id": "7",
            "server_id": "s",
            "token_url": "t",
            "client_id": "c",
            "client_secret_env": "",
            "redirect_uri": "r",
        },
    )
    assert resp.status_code == 401


def test_oauth_token_endpoint_returns_access_without_refresh(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    key = _register_node()
    mcp_user_token_store.put_token(
        "u1",
        "7",
        "crm",
        access_token="AT-valid",
        refresh_token="RT-secret",
        expires_at=10_000.0,
        scope="mcp.read",
        token_url="https://auth/token",
        client_id="c",
        client_secret_env="",
    )

    resp = client.post(
        "/nodes/node-a/mcp/oauth-token",
        headers=_bearer(key),
        json={"user_id": "u1", "agent_id": "7", "server_id": "crm"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "AT-valid"
    assert "RT-secret" not in resp.text
    assert "refresh_token" not in body


def test_oauth_token_missing_returns_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    key = _register_node()
    resp = client.post(
        "/nodes/node-a/mcp/oauth-token",
        headers=_bearer(key),
        json={"user_id": "nobody", "agent_id": "7", "server_id": "crm"},
    )
    assert resp.status_code == 404


def test_public_callback_completes_and_maps_status(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    async def fake_complete(code, state, **kwargs):
        return mcp_oauth_service.CallbackOutcome(
            code == "good", "ok" if code == "good" else "invalid_state", "d"
        )

    monkeypatch.setattr(mcp_oauth_service, "complete_callback", fake_complete)

    ok = client.get("/oauth/callback", params={"code": "good", "state": "st"})
    assert ok.status_code == 200

    bad = client.get("/oauth/callback", params={"code": "bad", "state": "st"})
    assert bad.status_code == 400
