from __future__ import annotations

import pytest
from fastapi.responses import StreamingResponse

from fleetent.identity import Principal
from fleetent.node.forwarder_contract import (
    DEFAULT_FORWARDER_DOMAIN,
    DEFAULT_FORWARDER_PORT,
    forwarder_base_url,
    forwarder_ws_url,
)


def test_forwarder_base_url_defaults_to_internal_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_FORWARDER_HOST_OVERRIDE", raising=False)

    url = forwarder_base_url("node-a")

    assert url == f"http://node-a.{DEFAULT_FORWARDER_DOMAIN}:{DEFAULT_FORWARDER_PORT}"


def test_forwarder_ws_url_defaults_to_internal_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_FORWARDER_HOST_OVERRIDE", raising=False)

    url = forwarder_ws_url("node-a")

    assert url == f"ws://node-a.{DEFAULT_FORWARDER_DOMAIN}:{DEFAULT_FORWARDER_PORT}"


def test_forwarder_base_url_uses_override_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")

    url = forwarder_base_url("node-a")

    assert url == f"http://127.0.0.1:{DEFAULT_FORWARDER_PORT}"


def test_forwarder_ws_url_uses_override_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")

    url = forwarder_ws_url("node-a")

    assert url == f"ws://127.0.0.1:{DEFAULT_FORWARDER_PORT}"


async def _collect_stream(response: StreamingResponse) -> bytes:
    out = b""
    async for chunk in response.body_iterator:
        out += chunk
    return out


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
        principal_header = '{"user_id":"u-edge","tenant_id":"tenant-1"}'
        assert str(request.url) == "http://node-a.internal:8786/forward/agents/support/chat"
        assert request.headers["Authorization"] == "Bearer ma-node-key"
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["X-Fleetent-Principal"] == principal_header
        assert request.content == b'{"message":"hi"}'
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: one\n\ndata: two\n\n",
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    response = await DirectHttpAgentTransport().chat(
        "node-a",
        "support",
        b'{"message":"hi"}',
        principal=Principal(user_id="u-edge", tenant_id="tenant-1"),
    )

    assert isinstance(response, StreamingResponse)
    assert await _collect_stream(response) == b"data: one\n\ndata: two\n\n"
