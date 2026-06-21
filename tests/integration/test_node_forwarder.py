from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app


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


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def test_forwarder_chat_requires_node_key_and_injects_tui_token(monkeypatch, tmp_path) -> None:
    import httpx

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["body"] = request.content
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: {\"type\":\"text\",\"content\":\"ok\"}\n\n",
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    rejected = client.post("/forward/agents/support/chat", json={"message": "hi"})
    accepted = client.post(
        "/forward/agents/support/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer " + "ma-" + "1" * 64},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert captured["url"] == "http://127.0.0.1:9011/chat"
    assert captured["auth"] == "Bearer ma-agent-token"
    assert captured["content_type"] == "application/json"
    assert json.loads(captured["body"]) == {"message": "hi"}


def test_forwarder_ws_requires_node_key(tmp_path) -> None:
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/forward/agents/support/ws"):
            pass
