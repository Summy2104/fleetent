from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import anyio
import httpx
import websockets
from fastapi import HTTPException, WebSocket
from fastapi.responses import Response, StreamingResponse
from starlette.websockets import WebSocketDisconnect

from fleetent.node.forwarder_contract import forwarder_base_url, forwarder_ws_url
from fleetent.platform.node_management import node_store


class AgentTransport(Protocol):
    async def chat(
        self,
        node_id: str,
        agent_name: str,
        body: bytes,
        *,
        content_type: str = "application/json",
    ) -> Response: ...

    async def ws(self, node_id: str, agent_name: str, websocket: WebSocket) -> None: ...


class DirectHttpAgentTransport:
    async def chat(
        self,
        node_id: str,
        agent_name: str,
        body: bytes,
        *,
        content_type: str = "application/json",
    ) -> Response:
        # Client is NOT wrapped in async with — its lifecycle is bound to _iter() so
        # the connection stays open until the StreamingResponse body is fully consumed.
        client = httpx.AsyncClient(timeout=None)
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    f"{forwarder_base_url(node_id)}/forward/agents/{agent_name}/chat",
                    content=body,
                    headers={
                        "Authorization": f"Bearer {_node_service_key(node_id)}",
                        "Content-Type": content_type,
                    },
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

    async def ws(self, node_id: str, agent_name: str, websocket: WebSocket) -> None:
        try:
            async with websockets.connect(
                f"{forwarder_ws_url(node_id)}/forward/agents/{agent_name}/ws",
                additional_headers={"Authorization": f"Bearer {_node_service_key(node_id)}"},
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


def _node_service_key(node_id: str) -> str:
    key = node_store.get_node_service_key(node_id)
    if not key:
        raise HTTPException(status_code=503, detail=f"node {node_id!r} service key unavailable")
    return key
