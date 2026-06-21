from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import WebSocket
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse

from fleetent import server, user_store
from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app as build_node_forwarder_app
from fleetent.runtime import agent_app


class _Backend:
    def gateway_port(self, agent_name: str) -> int | None:
        assert agent_name == "support"
        return 9011

    def spawn(self, agent_name: str, env=None) -> None:
        raise NotImplementedError

    def stop(self, agent_name: str) -> None:
        raise NotImplementedError

    def is_alive(self, agent_name: str) -> int | None:
        raise NotImplementedError


def _admin_user() -> user_store.User:
    return user_store.User(
        id="admin-1",
        name="Admin",
        created_at="2026-06-03T00:00:00+00:00",
        email="admin@example.com",
        role="admin",
        status="active",
        must_reset=0,
        password_hash="x",
    )


def test_admin_chat_ingress_reaches_node_forwarder_and_agent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import fleetent.runtime.loop as loop_mod
    from fleetent.platform.node_management.agent_transport import DirectHttpAgentTransport

    agent_home = tmp_path / "agents" / "support"
    agent_home.mkdir(parents=True)
    (agent_home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_stream(message: str, **kwargs):
        captured["principal"] = kwargs["principal"]
        yield {"type": "text", "content": f"echo:{message}"}

    monkeypatch.setattr(loop_mod, "run_stream", fake_run_stream)
    monkeypatch.setattr(agent_app.LocalBearerAdapter, "__call__", lambda self, _token: None)
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-agent-token")
    agent = agent_app.build_app("support")

    node_cfg = NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-node-key",
        home_dir=tmp_path,
        interval_seconds=10,
    )
    node_forwarder = build_node_forwarder_app(node_cfg, _Backend())

    async def fake_send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        if request.url.host == "node-a.internal":
            response = await httpx.ASGITransport(app=node_forwarder).handle_async_request(request)
            return response
        if request.url.host == "127.0.0.1" and request.url.port == 9011:
            captured["agent_auth"] = request.headers.get("Authorization")
            response = await httpx.ASGITransport(app=agent).handle_async_request(request)
            return response
        raise AssertionError(f"unexpected upstream request: {request.url}")

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    monkeypatch.setattr(server, "_agent_transport", DirectHttpAgentTransport())
    monkeypatch.setattr(
        "fleetent.platform.node_management.agent_transport.forwarder_base_url",
        lambda node_id: "http://node-a.internal:8786",
    )
    monkeypatch.setattr(
        "fleetent.platform.node_management.agent_transport.node_store.get_node_service_key",
        lambda node_id: "ma-node-key",
    )
    monkeypatch.setattr(server.auth, "validate_session", lambda token, idle: "admin-1")
    monkeypatch.setattr(server.auth, "has_role", lambda user, roles: True)
    monkeypatch.setattr(server.user_store, "get_by_id", lambda user_id: _admin_user())
    monkeypatch.setattr(server.agent_store, "get_by_name", lambda name: SimpleNamespace(id=7, name=name))
    monkeypatch.setattr(
        server.placement_store,
        "get_for_agent",
        lambda agent_id: {"agent_id": agent_id, "node_id": "node-a"},
    )

    client = TestClient(server.app)
    response = client.post(
        "/admin/agents/support/chat",
        json={"message": "hi"},
        headers={"Authorization": "Session sess-1"},
    )

    assert response.status_code == 200
    assert "echo:hi" in response.text
    assert captured["agent_auth"] == "Bearer ma-agent-token"
    principal = captured["principal"]
    assert getattr(principal, "user_id") == "local"


def test_managed_agent_chat_routes_by_placement_and_requires_admin_session(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTransport:
        async def chat(
            self,
            node_id: str,
            agent_name: str,
            body: bytes,
            *,
            content_type: str = "application/json",
        ):
            captured["node_id"] = node_id
            captured["agent_name"] = agent_name
            captured["body"] = body
            captured["content_type"] = content_type

            async def _iter():
                yield b"data: ok\n\n"

            return StreamingResponse(_iter(), media_type="text/event-stream")

        async def ws(self, node_id: str, agent_name: str, websocket: WebSocket) -> None:
            captured["ws_node_id"] = node_id
            await websocket.accept()
            await websocket.send_text('{"type":"ready"}')
            await websocket.close()

    monkeypatch.setattr(server, "_agent_transport", FakeTransport())
    monkeypatch.setattr(server.auth, "validate_session", lambda token, idle: "admin-1")
    monkeypatch.setattr(server.auth, "has_role", lambda user, roles: True)
    monkeypatch.setattr(server.user_store, "get_by_id", lambda user_id: _admin_user())
    monkeypatch.setattr(server.agent_store, "get_by_name", lambda name: SimpleNamespace(id=7, name=name))
    monkeypatch.setattr(
        server.placement_store,
        "get_for_agent",
        lambda agent_id: {"agent_id": agent_id, "node_id": "node-a"},
    )

    client = TestClient(server.app)

    rejected = client.post("/admin/agents/support/chat", json={"message": "hi"})
    accepted = client.post(
        "/admin/agents/support/chat",
        json={"message": "hi"},
        headers={"Authorization": "Session sess-1"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert captured["node_id"] == "node-a"
    assert captured["agent_name"] == "support"
    assert captured["body"] == b'{"message":"hi"}'
    assert captured["content_type"] == "application/json"

    with client.websocket_connect(
        "/admin/agents/support/ws",
        headers={"Authorization": "Session sess-1"},
    ) as ws:
        assert ws.receive_text() == '{"type":"ready"}'
