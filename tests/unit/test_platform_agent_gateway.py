from __future__ import annotations

import pytest
from fastapi.responses import StreamingResponse


async def _collect_stream(response: StreamingResponse) -> bytes:
    out = b""
    async for chunk in response.body_iterator:
        out += chunk
    return out


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


@pytest.mark.asyncio
async def test_direct_http_transport_relays_chat_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from fleetent.platform.node_management.agent_transport import DirectHttpAgentTransport

    monkeypatch.setattr(
        "fleetent.platform.node_management.agent_transport.forwarder_base_url",
        lambda node_id: "http://node-a.internal:8786",
    )
    monkeypatch.setattr(
        "fleetent.platform.node_management.agent_transport.node_store.get_node_service_key",
        lambda node_id: "ma-node-key",
    )

    async def fake_send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        assert str(request.url) == "http://node-a.internal:8786/forward/agents/support/chat"
        assert request.headers["Authorization"] == "Bearer ma-node-key"
        assert request.headers["Content-Type"] == "application/json"
        assert request.content == b'{"message":"hi"}'
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: one\n\ndata: two\n\n",
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    response = await DirectHttpAgentTransport().chat("node-a", "support", b'{"message":"hi"}')

    assert isinstance(response, StreamingResponse)
    assert await _collect_stream(response) == b"data: one\n\ndata: two\n\n"
