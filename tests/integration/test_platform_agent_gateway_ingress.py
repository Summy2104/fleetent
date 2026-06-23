from __future__ import annotations

import asyncio
import contextlib
import socket as _sock
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from fleetent import server, user_store
from fleetent.node.config import NodeConfig
from fleetent.node.forwarder import build_app as build_node_forwarder_app
from fleetent.runtime import agent_app


class _Backend:
    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        del tenant_id
        assert agent_name == "support"
        return 9011

    def spawn(self, agent_name: str, tenant_id: str = "default", env=None) -> None:
        del agent_name, tenant_id, env
        raise NotImplementedError

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:
        del agent_name, tenant_id
        raise NotImplementedError

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        del agent_name, tenant_id
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

    agent_home = tmp_path / "tenants" / "default" / "agents" / "support"
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
    monkeypatch.setattr(
        server.agent_store, "get_by_name", lambda name: SimpleNamespace(id=7, name=name)
    )
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
    assert principal.user_id == "admin-1"  # type: ignore[union-attr]
    assert principal.tenant_id == "default"  # type: ignore[union-attr]


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
            principal=None,
        ):
            captured["node_id"] = node_id
            captured["agent_name"] = agent_name
            captured["body"] = body
            captured["content_type"] = content_type
            captured["principal"] = principal

            async def _iter():
                yield b"data: ok\n\n"

            return StreamingResponse(_iter(), media_type="text/event-stream")

        async def ws(
            self,
            node_id: str,
            agent_name: str,
            websocket: WebSocket,
            *,
            principal=None,
        ) -> None:
            captured["ws_node_id"] = node_id
            captured["ws_principal"] = principal
            await websocket.accept()
            await websocket.send_text('{"type":"ready"}')
            await websocket.close()

    monkeypatch.setattr(server, "_agent_transport", FakeTransport())
    monkeypatch.setattr(server.auth, "validate_session", lambda token, idle: "admin-1")
    monkeypatch.setattr(server.auth, "has_role", lambda user, roles: True)
    monkeypatch.setattr(server.user_store, "get_by_id", lambda user_id: _admin_user())
    monkeypatch.setattr(
        server.agent_store, "get_by_name", lambda name: SimpleNamespace(id=7, name=name)
    )
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
    assert captured["principal"].user_id == "admin-1"
    assert captured["principal"].tenant_id == "default"

    with client.websocket_connect(
        "/admin/agents/support/ws",
        headers={"Authorization": "Session sess-1"},
    ) as ws:
        assert ws.receive_text() == '{"type":"ready"}'
    assert captured["ws_principal"].user_id == "admin-1"
    assert captured["ws_principal"].tenant_id == "default"


async def test_direct_http_transport_chat_streams_complete_body_over_real_socket(
    monkeypatch,
) -> None:
    """Regression: DirectHttpAgentTransport.chat must relay the complete SSE body.

    The bug: async with httpx.AsyncClient closed the client on return, before
    Starlette consumed the StreamingResponse body iterator. Real loopback socket
    is required — in-memory mocks bypass the timing. Body iterator is consumed
    after chat() returns to reproduce the exact bug timing.
    """
    from fleetent.platform.node_management.agent_transport import DirectHttpAgentTransport

    expected_chunks = [b"data: chunk1\n\n", b"data: chunk2\n\n", b"data: chunk3\n\n"]

    with _sock.socket() as s:
        s.bind(("127.0.0.1", 0))
        forwarder_port = s.getsockname()[1]

    # Real streaming "forwarder" endpoint on a real socket
    fake_forwarder = FastAPI()

    @fake_forwarder.post("/forward/agents/support/chat")
    async def _fwd_chat() -> StreamingResponse:
        async def _body():
            for chunk in expected_chunks:
                yield chunk
                await asyncio.sleep(0.005)

        return StreamingResponse(_body(), media_type="text/event-stream")

    srv = uvicorn.Server(
        uvicorn.Config(fake_forwarder, host="127.0.0.1", port=forwarder_port, log_level="error")
    )
    serve_task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.01)

    try:
        monkeypatch.setattr(
            "fleetent.platform.node_management.agent_transport.forwarder_base_url",
            lambda node_id: f"http://127.0.0.1:{forwarder_port}",
        )
        monkeypatch.setattr(
            "fleetent.platform.node_management.agent_transport.node_store.get_node_service_key",
            lambda node_id: "ma-node-key",
        )

        transport = DirectHttpAgentTransport()

        body = b""
        try:
            # chat() returns a StreamingResponse; async with inside chat() exits here,
            # closing the httpx client — the bug is that the TCP connection also closes.
            response = await transport.chat(
                "node-a", "support", b'{"message":"ping"}', content_type="application/json"
            )
            # Consume body_iterator exactly as Starlette would after the handler returns
            received: list[bytes] = []
            async for chunk in response.body_iterator:  # type: ignore[union-attr]
                received.append(chunk)
            body = b"".join(received)
        except Exception:
            body = b""

        assert body, (
            "body must not be empty (regression: premature httpx client close yielded 0 bytes)"
        )
        for chunk in expected_chunks:
            assert chunk in body, f"missing SSE chunk {chunk!r} from DirectHttpAgentTransport.chat"
    finally:
        srv.should_exit = True
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(serve_task, timeout=5.0)
