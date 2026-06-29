"""Integration: managed per-user MCP OAuth happy-path end-to-end (platform chain).

Exercises the substantive new chain through the platform app: a node registers a pending
authorization, the OAuth provider redirects the user's browser to the public callback
(which exchanges the code against a mocked token endpoint and stores the token), and the
node later fetches a valid access token — never the refresh token. The agent↔node loopback
hop is covered by test_node_loopback_oauth / test_managed_oauth.
"""

from __future__ import annotations

import httpx
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

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


@respx.mock
def test_managed_happy_path_pending_callback_then_token(tmp_path, monkeypatch) -> None:
    respx.post("https://auth.internal/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "AT-managed",
                "refresh_token": "RT-secret",
                "expires_in": 3600,
                "scope": "mcp.read",
            },
        )
    )
    client = _client(tmp_path, monkeypatch)
    key, _ = node_store.register_node("node-a", name="Node A")
    bearer = {"Authorization": f"Bearer {key}"}

    # 1) Agent (via node) registers pending-auth before sending the authorization link.
    pend = client.post(
        "/nodes/node-a/mcp/oauth-pending",
        headers=bearer,
        json={
            "state": "st-e2e",
            "code_verifier": "verifier-e2e",
            "user_id": "u1",
            "agent_id": "alpha",
            "server_id": "crm",
            "token_url": "https://auth.internal/token",
            "client_id": "fleetent-crm",
            "client_secret_env": "",
            "redirect_uri": "https://platform/oauth/callback",
        },
    )
    assert pend.status_code == 200

    # 2) The provider redirects the user's browser to the public callback -> code exchange.
    cb = client.get("/oauth/callback", params={"code": "auth-code", "state": "st-e2e"})
    assert cb.status_code == 200

    # 3) Later, the agent (via node) fetches a valid access token; refresh token stays on platform.
    tok = client.post(
        "/nodes/node-a/mcp/oauth-token",
        headers=bearer,
        json={"user_id": "u1", "agent_id": "alpha", "server_id": "crm"},
    )
    assert tok.status_code == 200
    assert tok.json()["access_token"] == "AT-managed"
    assert "RT-secret" not in tok.text

    # State is one-time: a replayed callback no longer succeeds.
    replay = client.get("/oauth/callback", params={"code": "auth-code", "state": "st-e2e"})
    assert replay.status_code == 400


def test_managed_oauth_module_does_not_import_platform() -> None:
    # Contract: the agent-side managed wiring MUST NOT import platform.* (agent⊥platform),
    # so it stays usable under the no-platform standalone baseline.
    import ast
    import pathlib

    src = pathlib.Path("src/fleetent/integrations/mcp/managed_oauth.py").read_text()
    tree = ast.parse(src)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    assert not any(m.startswith("fleetent.platform") for m in imported), imported
