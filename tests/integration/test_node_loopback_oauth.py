"""Integration: node agent→node loopback OAuth broker + spawn env injection (slice 2).

The forwarder exposes agent-facing /agent/{name}/mcp/oauth-{pending,token} routes that
authenticate with the agent's own TUI token (never the node service key) and forward to
platform holding the service key. The local backend injects FLEETENT_NODE_LOOPBACK_URL at
spawn so the managed agent knows where its broker is.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app


def _config(home: Path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-node-secret",
        home_dir=home,
    )


def _write_agent_env(home: Path, agent_name: str, token: str) -> None:
    env_dir = home / "tenants" / "default" / "agents" / agent_name
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text(f"FLEETENT_TUI_TOKEN={token}\n", encoding="utf-8")


class _StubBackend:
    def agent_endpoint(self, agent_name, tenant_id="default"):
        return ("127.0.0.1", 9999)


@respx.mock
def test_loopback_oauth_pending_auths_with_tui_token_and_forwards_with_service_key(tmp_path):
    home = tmp_path / "home"
    _write_agent_env(home, "alpha", "tui-tok-123")
    route = respx.post("https://platform.internal/nodes/node-a/mcp/oauth-pending").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = TestClient(build_app(_config(home), _StubBackend()))

    resp = client.post(
        "/agent/alpha/mcp/oauth-pending",
        headers={"Authorization": "Bearer tui-tok-123"},
        json={"state": "s"},
    )

    assert resp.status_code == 200
    assert route.called
    # Forwarded to platform with the node service key (never exposed to the agent).
    assert route.calls.last.request.headers["authorization"] == "Bearer ma-node-secret"


@respx.mock
def test_loopback_oauth_token_forwards_and_returns_access(tmp_path):
    home = tmp_path / "home"
    _write_agent_env(home, "alpha", "tui-tok-123")
    respx.post("https://platform.internal/nodes/node-a/mcp/oauth-token").mock(
        return_value=httpx.Response(200, json={"access_token": "AT"})
    )
    client = TestClient(build_app(_config(home), _StubBackend()))

    resp = client.post(
        "/agent/alpha/mcp/oauth-token",
        headers={"Authorization": "Bearer tui-tok-123"},
        json={"user_id": "u", "agent_id": "alpha", "server_id": "crm"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "AT"


def test_loopback_rejects_wrong_agent_token(tmp_path):
    home = tmp_path / "home"
    _write_agent_env(home, "alpha", "tui-tok-123")
    client = TestClient(build_app(_config(home), _StubBackend()))

    resp = client.post(
        "/agent/alpha/mcp/oauth-token",
        headers={"Authorization": "Bearer wrong-token"},
        json={"user_id": "u", "agent_id": "alpha", "server_id": "crm"},
    )
    assert resp.status_code == 401


def test_reconcile_writes_loopback_url_into_agent_env(tmp_path):
    # Env-only contract: the process backend never injects env= (see test_backend); the
    # loopback URL (managed signal) reaches the agent through its .env, written by reconcile.
    from fleetent.node.reconcile import NodeReconciler

    reconciler = NodeReconciler(_config(tmp_path), _StubBackend())
    reconciler._write_home("alpha", "default", {"name": "alpha"}, secrets={})

    env_text = (tmp_path / "tenants" / "default" / "agents" / "alpha" / ".env").read_text(
        encoding="utf-8"
    )
    assert "FLEETENT_NODE_LOOPBACK_URL=http://127.0.0.1:8767" in env_text
