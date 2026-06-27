from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import httpx
import websockets
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import Response, StreamingResponse
from starlette.websockets import WebSocketDisconnect

from fleetent.identity import INGRESS_PRINCIPAL_HEADER
from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.skill_deployer import bundle_skill_directory


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

    def _agent_endpoint(agent_name: str, tenant_id: str = "default") -> tuple[str, int]:
        try:
            return backend.agent_endpoint(agent_name, tenant_id)
        except KeyError:
            raise HTTPException(
                status_code=503, detail=f"agent {agent_name!r} is unavailable"
            ) from None

    def _agent_tui_token(agent_name: str, tenant_id: str = "default") -> str:
        env_path = Path(config.home_dir) / "tenants" / tenant_id / "agents" / agent_name / ".env"
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
        tenant_id = request.headers.get("x-fleetent-tenant-id", "default")
        host, port = _agent_endpoint(agent_name, tenant_id)
        token = _agent_tui_token(agent_name, tenant_id)
        body = await request.body()
        headers = {"Authorization": f"Bearer {token}"}
        if request.headers.get("content-type"):
            headers["Content-Type"] = request.headers["content-type"]
        if request.headers.get(INGRESS_PRINCIPAL_HEADER):
            headers[INGRESS_PRINCIPAL_HEADER] = request.headers[INGRESS_PRINCIPAL_HEADER]
        # Client is NOT wrapped in async with — its lifecycle is bound to _iter() so
        # the connection stays open until the StreamingResponse body is fully consumed.
        client = httpx.AsyncClient(timeout=None)
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    f"http://{host}:{port}/chat",
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

    @app.websocket("/forward/agents/{agent_name}/ws")
    async def forward_ws(websocket: WebSocket, agent_name: str) -> None:
        try:
            _check_node_key(websocket.headers.get("authorization"))
        except HTTPException:
            await websocket.close(code=1008)
            return
        tenant_id = websocket.headers.get("x-fleetent-tenant-id", "default")
        host, port = _agent_endpoint(agent_name, tenant_id)
        token = _agent_tui_token(agent_name, tenant_id)
        upstream_url = f"ws://{host}:{port}/ws"
        try:
            upstream_headers = {"Authorization": f"Bearer {token}"}
            if websocket.headers.get(INGRESS_PRINCIPAL_HEADER.lower()):
                upstream_headers[INGRESS_PRINCIPAL_HEADER] = websocket.headers[
                    INGRESS_PRINCIPAL_HEADER.lower()
                ]
            async with websockets.connect(
                upstream_url,
                additional_headers=upstream_headers,
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

    @app.get("/forward/agents/{agent_name}/skills/{skill_name}/bundle")
    async def forward_skill_bundle(
        agent_name: str,
        skill_name: str,
        request: Request,
        authorization: str | None = Header(None),
    ) -> Response:
        _check_node_key(authorization)
        tenant_id = request.headers.get("x-fleetent-tenant-id", "default")
        skill_dir = (
            Path(config.home_dir)
            / "tenants"
            / tenant_id
            / "agents"
            / agent_name
            / "skills"
            / skill_name
        )
        if not skill_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"skill {skill_name!r} not found")
        return Response(content=bundle_skill_directory(skill_dir), media_type="application/gzip")

    return app
