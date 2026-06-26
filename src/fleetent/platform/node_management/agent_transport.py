from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import AsyncIterator
from typing import Protocol

import anyio
import httpx
import websockets
from fastapi import HTTPException, WebSocket
from fastapi.responses import Response, StreamingResponse
from starlette.websockets import WebSocketDisconnect

from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, encode_ingress_principal
from fleetent.node.forwarder_contract import (
    DEFAULT_FORWARDER_PORT,
    forwarder_base_url,
    forwarder_ws_url,
)
from fleetent.platform.node_management import node_store

_logger = logging.getLogger(__name__)

# RFC-1123 hostname: dot-separated labels of [A-Za-z0-9-], each 1-63 chars, not
# starting/ending with a hyphen; total length <= 253. Anchored, so any value with
# URL-smuggling characters (/, ?, #, @, :, whitespace, _) fails to match.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _is_valid_forward_host(host: str) -> bool:
    """Whether a node-reported forward_host is safe to interpolate into a dial URL.

    The value is self-reported by the node and spliced into ``http://{host}:port``.
    Without this guard a value carrying URL-smuggling characters (``@``, ``/``,
    ``?``, ``#``, ``:``, whitespace) could redirect the platform's request to a
    different host (SSRF). Accept only a bare IPv4 literal or RFC-1123 hostname.
    Loopback/private addresses are intentionally allowed — colocated on-prem nodes
    legitimately advertise ``127.0.0.1`` or internal IPs.
    """
    try:
        return ipaddress.ip_address(host).version == 4
    except ValueError:
        return bool(_HOSTNAME_RE.match(host))


class AgentTransport(Protocol):
    async def chat(
        self,
        node_id: str,
        agent_name: str,
        body: bytes,
        *,
        content_type: str = "application/json",
        principal: Principal | None = None,
    ) -> Response: ...

    async def ws(
        self,
        node_id: str,
        agent_name: str,
        websocket: WebSocket,
        *,
        principal: Principal | None = None,
    ) -> None: ...


class DirectHttpAgentTransport:
    async def chat(
        self,
        node_id: str,
        agent_name: str,
        body: bytes,
        *,
        content_type: str = "application/json",
        principal: Principal | None = None,
    ) -> Response:
        headers = {
            "Authorization": f"Bearer {_node_service_key(node_id)}",
            "Content-Type": content_type,
        }
        if principal is not None:
            headers[INGRESS_PRINCIPAL_HEADER] = encode_ingress_principal(principal)
        # Client is NOT wrapped in async with — its lifecycle is bound to _iter() so
        # the connection stays open until the StreamingResponse body is fully consumed.
        client = httpx.AsyncClient(timeout=None)
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    f"{_forwarder_base_url(node_id)}/forward/agents/{agent_name}/chat",
                    content=body,
                    headers=headers,
                ),
                stream=True,
            )
        except Exception:
            await client.aclose()
            raise
        if upstream.status_code >= 400:
            content = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            return Response(
                content=content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type"),
            )

        async def _iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            _iter(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
        )

    async def ws(
        self,
        node_id: str,
        agent_name: str,
        websocket: WebSocket,
        *,
        principal: Principal | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {_node_service_key(node_id)}"}
        if principal is not None:
            headers[INGRESS_PRINCIPAL_HEADER] = encode_ingress_principal(principal)
        try:
            async with websockets.connect(
                f"{_forwarder_ws_url(node_id)}/forward/agents/{agent_name}/ws",
                additional_headers=headers,
            ) as upstream:
                await websocket.accept()

                async def _client_to_upstream() -> None:
                    while True:
                        await upstream.send(await websocket.receive_text())

                async def _upstream_to_client() -> None:
                    async for message in upstream:
                        await websocket.send_text(str(message))

                async with anyio.create_task_group() as task_group:
                    task_group.start_soon(_client_to_upstream)
                    task_group.start_soon(_upstream_to_client)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


def _forwarder_base_url(node_id: str) -> str:
    """Resolve the node forwarder base URL, preferring the node-reported address.

    Priority: reported forward_host (DB) → FLEETENT_FORWARDER_HOST_OVERRIDE → {node_id}.internal.
    Reading the reported address here (platform side) keeps node/ off the management DB.
    """
    host = node_store.get_forward_host(node_id)
    if host and _is_valid_forward_host(host):
        return f"http://{host}:{DEFAULT_FORWARDER_PORT}"
    if host:
        _logger.warning("ignoring malformed reported forward_host %r for node %s", host, node_id)
    return forwarder_base_url(node_id)


def _forwarder_ws_url(node_id: str) -> str:
    host = node_store.get_forward_host(node_id)
    if host and _is_valid_forward_host(host):
        return f"ws://{host}:{DEFAULT_FORWARDER_PORT}"
    if host:
        _logger.warning("ignoring malformed reported forward_host %r for node %s", host, node_id)
    return forwarder_ws_url(node_id)


def _node_service_key(node_id: str) -> str:
    key = node_store.get_node_service_key(node_id)
    if not key:
        raise HTTPException(status_code=503, detail=f"node {node_id!r} service key unavailable")
    return key
