"""node loopback identity/address forward endpoints (agent-hosted-im)."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app


class _Backend:
    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        return 9011

    def agent_endpoint(self, agent_name: str, tenant_id: str = "default") -> tuple[str, int]:
        return ("agent-" + agent_name, 9011)

    def spawn(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        raise NotImplementedError

    def stop(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        raise NotImplementedError

    def is_alive(self, *a, **k):  # noqa: ANN002, ANN003
        raise NotImplementedError


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _seed_agent_env(tmp_path, agent="support", tenant="default") -> None:
    home = tmp_path / "tenants" / tenant / "agents" / agent
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")


def _run(tmp_path, monkeypatch, suffix: str, body: dict, upstream: dict):
    _seed_agent_env(tmp_path)
    captured: dict[str, object] = {}

    async def fake_send(self, request: httpx.Request, **kwargs) -> httpx.Response:  # noqa: ANN003
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        return httpx.Response(200, json=upstream)

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    client = TestClient(build_app(_config(tmp_path), _Backend()))
    resp = client.post(
        f"/agent/support/identity/{suffix}",
        json=body,
        headers={"Authorization": "Bearer ma-agent-token"},
    )
    return resp, captured


def test_identity_resolve_forwards_with_service_key(tmp_path, monkeypatch) -> None:
    resp, captured = _run(
        tmp_path,
        monkeypatch,
        "resolve",
        {"tenant_id": "default", "channel": "slack", "platform_user_id": "U1"},
        {"user_id": "user-42", "tenant_id": "default"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user-42"
    assert captured["url"] == "https://platform.internal/nodes/node-a/identity/resolve"
    assert captured["auth"] == "Bearer ma-" + "1" * 64  # node service key, not the agent token
    assert json.loads(captured["body"])["platform_user_id"] == "U1"


def test_identity_addresses_forwards_with_service_key(tmp_path, monkeypatch) -> None:
    resp, captured = _run(
        tmp_path,
        monkeypatch,
        "addresses",
        {"user_id": "user-42"},
        {"addresses": [{"platform": "slack", "platform_user_id": "U1"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["addresses"][0]["platform"] == "slack"
    assert captured["url"] == "https://platform.internal/nodes/node-a/identity/addresses"
    assert captured["auth"] == "Bearer ma-" + "1" * 64


def test_identity_resolve_rejects_wrong_agent_token(tmp_path, monkeypatch) -> None:
    _seed_agent_env(tmp_path)
    client = TestClient(build_app(_config(tmp_path), _Backend()))
    resp = client.post(
        "/agent/support/identity/resolve",
        json={"tenant_id": "default", "channel": "slack", "platform_user_id": "U1"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401
