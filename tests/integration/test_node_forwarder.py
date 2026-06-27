from __future__ import annotations

import asyncio
import contextlib
import io
import json
import socket as _sock
import tarfile

import httpx
import pytest
import uvicorn
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app


class _Backend:
    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        assert agent_name == "support"
        assert tenant_id == "tenant-1"
        return 9011

    def agent_endpoint(self, agent_name: str, tenant_id: str = "default") -> tuple[str, int]:
        assert agent_name == "support"
        assert tenant_id == "tenant-1"
        return ("agent-support", 9011)

    def spawn(self, agent_name: str, tenant_id: str = "default", env=None) -> None:
        raise NotImplementedError

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:
        raise NotImplementedError

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        raise NotImplementedError


def _home(tmp_path, agent_name: str = "support", tenant_id: str = "tenant-1"):
    return tmp_path / "tenants" / tenant_id / "agents" / agent_name


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

    home = _home(tmp_path)
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
            content=b'data: {"type":"text","content":"ok"}\n\n',
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    rejected = client.post("/forward/agents/support/chat", json={"message": "hi"})
    accepted = client.post(
        "/forward/agents/support/chat",
        json={"message": "hi"},
        headers={
            "Authorization": "Bearer " + "ma-" + "1" * 64,
            "X-Fleetent-Tenant-Id": "tenant-1",
        },
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert captured["url"] == "http://agent-support:9011/chat"
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
    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    chunks = [b"data: chunk1\n\n", b"data: chunk2\n\n", b"data: chunk3\n\n"]

    with _sock.socket() as s:
        s.bind(("127.0.0.1", 0))
        upstream_port = s.getsockname()[1]

    upstream_app = FastAPI()

    @upstream_app.post("/chat")
    async def _upstream_chat() -> StreamingResponse:
        async def _body():
            for chunk in chunks:
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
            def gateway_port(self, name: str, tenant_id: str = "default") -> int | None:
                assert tenant_id == "tenant-1"
                return upstream_port

            def agent_endpoint(self, name: str, tenant_id: str = "default") -> tuple[str, int]:
                assert tenant_id == "tenant-1"
                return ("127.0.0.1", upstream_port)

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
                        "X-Fleetent-Tenant-Id": "tenant-1",
                    },
                )
            body = response.content
        except Exception:
            body = b""

        assert body, (
            "body must not be empty (regression: premature httpx client close yielded 0 bytes)"
        )
        for chunk in chunks:
            assert chunk in body, f"missing SSE chunk {chunk!r} from relayed body"
    finally:
        srv.should_exit = True
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(serve_task, timeout=5.0)


async def test_forward_chat_relays_ingress_principal_header_over_real_socket(tmp_path) -> None:
    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    with _sock.socket() as s:
        s.bind(("127.0.0.1", 0))
        upstream_port = s.getsockname()[1]

    captured: dict[str, str | None] = {}
    upstream_app = FastAPI()

    @upstream_app.post("/chat")
    async def _upstream_chat(request: Request) -> StreamingResponse:
        captured["principal_header"] = request.headers.get("x-fleetent-principal")

        async def _body():
            yield b'data: {"type":"text","content":"ok"}\n\n'

        return StreamingResponse(_body(), media_type="text/event-stream")

    srv = uvicorn.Server(
        uvicorn.Config(upstream_app, host="127.0.0.1", port=upstream_port, log_level="error")
    )
    serve_task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.01)

    try:

        class _RealBackend:
            def gateway_port(self, name: str, tenant_id: str = "default") -> int | None:
                assert tenant_id == "tenant-1"
                return upstream_port

            def agent_endpoint(self, name: str, tenant_id: str = "default") -> tuple[str, int]:
                assert tenant_id == "tenant-1"
                return ("127.0.0.1", upstream_port)

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

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=forwarder), base_url="http://testserver"
        ) as tc:
            response = await tc.post(
                "/forward/agents/support/chat",
                content=b'{"message":"ping"}',
                headers={
                    "Authorization": "Bearer " + "ma-" + "1" * 64,
                    "Content-Type": "application/json",
                    "X-Fleetent-Principal": '{"user_id":"operator-1","tenant_id":"tenant-1"}',
                    "X-Fleetent-Tenant-Id": "tenant-1",
                },
            )

        assert response.status_code == 200
        assert captured["principal_header"] == '{"user_id":"operator-1","tenant_id":"tenant-1"}'
    finally:
        srv.should_exit = True
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(serve_task, timeout=5.0)


def test_forwarder_ws_requires_node_key(tmp_path) -> None:
    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/forward/agents/support/ws"):
        pass


def test_forwarder_ws_relays_ingress_principal_header(monkeypatch, tmp_path) -> None:
    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class _FakeUpstream:
        async def send(self, message: str) -> None:
            return None

        def __aiter__(self):
            async def _iter():
                yield '{"type":"ready"}'

            return _iter()

    class _FakeConnect:
        async def __aenter__(self):
            return _FakeUpstream()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_connect(url: str, additional_headers: dict[str, str]):
        captured["url"] = url
        captured["headers"] = additional_headers
        return _FakeConnect()

    monkeypatch.setattr(websockets, "connect", fake_connect)
    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    with client.websocket_connect(
        "/forward/agents/support/ws",
        headers={
            "Authorization": "Bearer " + "ma-" + "1" * 64,
            "X-Fleetent-Principal": '{"user_id":"operator-1","tenant_id":"tenant-1"}',
            "X-Fleetent-Tenant-Id": "tenant-1",
        },
    ) as ws:
        assert ws.receive_text() == '{"type":"ready"}'

    assert captured["url"] == "ws://agent-support:9011/ws"
    assert captured["headers"] == {
        "Authorization": "Bearer ma-agent-token",
        "X-Fleetent-Principal": '{"user_id":"operator-1","tenant_id":"tenant-1"}',
    }


def test_forwarder_serves_local_skill_bundle_for_platform(tmp_path) -> None:
    home = _home(tmp_path)
    skill_dir = home / "skills" / "incident-review" / "scripts"
    skill_dir.mkdir(parents=True)
    (home / "skills" / "incident-review" / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: d\n---\nbody\n",
        encoding="utf-8",
    )
    (skill_dir / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")

    app = build_app(_config(tmp_path), _Backend())
    client = TestClient(app)

    response = client.get(
        "/forward/agents/support/skills/incident-review/bundle",
        headers={
            "Authorization": "Bearer " + "ma-" + "1" * 64,
            "X-Fleetent-Tenant-Id": "tenant-1",
        },
    )

    assert response.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        assert sorted(archive.getnames()) == [
            "incident-review/SKILL.md",
            "incident-review/scripts/helper.py",
        ]
