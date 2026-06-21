from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anyio
import httpx
import websockets
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import Response, StreamingResponse
from starlette.websockets import WebSocketDisconnect

from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        values[key.strip()] = val
    return values


def build_app(config: NodeConfig, backend: BaseProcessBackend) -> FastAPI:
    app = FastAPI(title=f"fleetent-node-forwarder:{config.node_id}")

    def _check_node_key(authorization: str | None) -> None:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        if authorization.removeprefix("Bearer ").strip() != config.service_key:
            raise HTTPException(status_code=401, detail="Invalid node API key")

    def _agent_port(agent_name: str) -> int:
        port = backend.gateway_port(agent_name)
        if port is None:
            raise HTTPException(status_code=503, detail=f"agent {agent_name!r} is unavailable")
        return port

    def _agent_tui_token(agent_name: str) -> str:
        env_path = Path(config.home_dir) / "agents" / agent_name / ".env"
        if not env_path.exists():
            raise HTTPException(status_code=503, detail=f"agent {agent_name!r} has no env scaffold")
        token = _parse_env(env_path.read_text(encoding="utf-8")).get("FLEETENT_TUI_TOKEN", "")
        if not token:
            raise HTTPException(status_code=503, detail=f"agent {agent_name!r} has no TUI token")
        return token

    @app.post("/forward/agents/{agent_name}/chat")
    async def forward_chat(
        agent_name: str,
        request: Request,
        authorization: str | None = Header(None),
    ) -> Response:
        _check_node_key(authorization)
        port = _agent_port(agent_name)
        token = _agent_tui_token(agent_name)
        body = await request.body()
        headers = {"Authorization": f"Bearer {token}"}
        if request.headers.get("content-type"):
            headers["Content-Type"] = request.headers["content-type"]
        async with httpx.AsyncClient(timeout=None) as client:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    f"http://127.0.0.1:{port}/chat",
                    content=body,
                    headers=headers,
                ),
                stream=True,
            )
            if upstream.status_code >= 400:
                content = await upstream.aread()
                await upstream.aclose()
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

            return StreamingResponse(
                _iter(),
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "text/event-stream"),
            )

    @app.websocket("/forward/agents/{agent_name}/ws")
    async def forward_ws(websocket: WebSocket, agent_name: str) -> None:
        try:
            _check_node_key(websocket.headers.get("authorization"))
        except HTTPException:
            await websocket.close(code=1008)
            return
        port = _agent_port(agent_name)
        token = _agent_tui_token(agent_name)
        upstream_url = f"ws://127.0.0.1:{port}/ws"
        try:
            async with websockets.connect(
                upstream_url,
                additional_headers={"Authorization": f"Bearer {token}"},
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
        except Exception:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close(code=1011)

    return app
