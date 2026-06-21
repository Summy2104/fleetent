from __future__ import annotations

import asyncio
import json
import socket as _sock

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
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


async def test_forward_chat_streams_complete_body_over_real_socket(tmp_path) -> None:
    """Regression: forward_chat must relay the complete SSE body to the caller.

    The bug: async with httpx.AsyncClient closed the client when forward_chat
    returned the StreamingResponse, before Starlette consumed the body iterator.
    A real loopback TCP connection is required — in-memory mocks bypass the timing
    because aiter_bytes() still works even after the client object is closed.
    """
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    CHUNKS = [b"data: chunk1\n\n", b"data: chunk2\n\n", b"data: chunk3\n\n"]

    with _sock.socket() as s:
        s.bind(("127.0.0.1", 0))
        upstream_port = s.getsockname()[1]

    upstream_app = FastAPI()

    @upstream_app.post("/chat")
    async def _upstream_chat() -> StreamingResponse:
        async def _body():
            for chunk in CHUNKS:
                yield chunk
                await asyncio.sleep(0.005)

        return StreamingResponse(_body(), media_type="text/event-stream")

    srv = uvicorn.Server(
        uvicorn.Config(upstream_app, host="127.0.0.1", port=upstream_port, log_level="error")
    )
    serve_task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.01)

    try:
        class _RealBackend:
            def gateway_port(self, name: str) -> int | None:
                return upstream_port

        forwarder = build_app(
            NodeConfig(
                platform_url="https://platform.internal",
                node_id="node-a",
                service_key="ma-" + "1" * 64,
                home_dir=tmp_path,
                interval_seconds=10,
            ),
            _RealBackend(),
        )

        body = b""
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=forwarder), base_url="http://testserver"
            ) as tc:
                response = await tc.post(
                    "/forward/agents/support/chat",
                    content=b'{"message":"ping"}',
                    headers={
                        "Authorization": "Bearer " + "ma-" + "1" * 64,
                        "Content-Type": "application/json",
                    },
                )
            body = response.content
        except Exception:
            body = b""

        assert body, "body must not be empty (regression: premature httpx client close yielded 0 bytes)"
        for chunk in CHUNKS:
            assert chunk in body, f"missing SSE chunk {chunk!r} from relayed body"
    finally:
        srv.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass


def test_forwarder_ws_requires_node_key(tmp_path) -> None:
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/forward/agents/support/ws"):
            pass
