"""Standalone agent runtime: boot one agent home as a self-contained process.

`fleetent agent run <agent-id>` loads a single agent home (`agent.yaml` + `.env` +
`data/` + local access), runs the agent loop, and brings up that agent's IM connectors —
with no platform service. Reuses the shared runtime libs (loop/run_stream, agent_config,
session, MCP, sandbox, the per-agent Slack supervisor) but as an agent-scoped runtime,
not the platform app (see openspec change ``agent-runtime-cli``). HTTP `/chat` + `/ws`
are served only when a port is given.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from fleetent import agent_config, paths
from fleetent.agent_config import AgentFile

if TYPE_CHECKING:
    from fastapi import FastAPI

    from fleetent.im_gateway.slack_supervisor import SlackSupervisor

logger = structlog.get_logger(__name__)


@dataclass
class AgentRuntime:
    """Handle for a running standalone agent: its definition, IM supervisor, app."""

    agent: AgentFile
    supervisor: SlackSupervisor
    app: FastAPI | None = None
    port: int | None = None

    async def stop(self) -> None:
        await self.supervisor.stop_all()


def resolve_home(agent_id: str, home: str | Path | None = None) -> Path:
    """Resolve the agent home: explicit ``home`` wins, else ``FLEETENT_HOME/<agent-id>``."""
    if home is not None:
        return Path(home)
    return paths.base_dir() / agent_id


async def _start_infra(agent: AgentFile) -> None:
    """Best-effort process infrastructure: sandbox probe, per-agent MCP, session upkeep.

    Each step mirrors the platform lifespan but scoped to this one agent; a failure is
    logged and never aborts boot (same best-effort posture as the platform).
    """
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    await sandbox_enablement.get_effective_mode()  # one-time Docker probe, cached
    if agent.mcp_servers:
        from fleetent.integrations import mcp as mcp_client
        from fleetent.integrations.mcp.client import McpServerConfig

        configs = [
            McpServerConfig(
                id=s.id,
                transport=s.transport,
                url=s.url,
                auth_type=s.auth_type,
                api_key_env=s.api_key_env,
                command=s.command,
                args=list(s.args),
                env=dict(s.env),
            )
            for s in agent.mcp_servers
        ]
        try:
            await mcp_client.register_all(configs)
        except Exception as exc:  # noqa: BLE001 — MCP unavailable must not abort boot
            logger.warning("agent_runtime_mcp_register_failed", error=str(exc))
    session_mgr.start_session_maintenance()


async def boot(
    agent_id: str,
    *,
    home: str | Path | None = None,
    port: int | None = None,
    supervisor: SlackSupervisor | None = None,
    start_im: bool = True,
    with_infra: bool = True,
) -> AgentRuntime:
    """Boot a single self-contained agent: load its home, bind IM, optionally serve HTTP.

    Publishes a single-agent index so routing resolves only this agent. Starts the
    agent's Slack connector (the only per-agent connector in the home schema). With
    ``port``, builds the agent app serving ``/chat`` + ``/ws``.
    """
    from fleetent.skills import scan as scan_skills
    from fleetent.tools.plugin_loader import load_plugins

    home_dir = resolve_home(agent_id, home)
    agent = agent_config.scan_home(home_dir)
    scan_skills()
    load_plugins()

    if with_infra:
        await _start_infra(agent)

    if supervisor is None:
        from fleetent.im_gateway.slack_supervisor import SlackSupervisor

        supervisor = SlackSupervisor()
    if start_im:
        await supervisor.start(agent.name)

    app = build_app(agent.name) if port is not None else None
    logger.info("agent_runtime_booted", agent=agent.name, http_port=port, im=start_im)
    return AgentRuntime(agent=agent, supervisor=supervisor, app=app, port=port)


async def _wait_forever() -> None:
    """Block until cancelled (IM-only foreground runtime has no HTTP server to await)."""
    import asyncio

    await asyncio.Event().wait()


async def serve(agent_id: str, *, port: int | None = None, home: str | Path | None = None) -> None:
    """Boot the agent and run it in the foreground until cancelled.

    With ``port`` the agent app is served over HTTP (``/chat`` + ``/ws``); without it the
    process runs IM-only with no HTTP listener.
    """
    rt = await boot(agent_id, home=home, port=port)
    try:
        if port is not None:
            import uvicorn

            assert rt.app is not None  # boot() builds the app whenever a port is given
            server = uvicorn.Server(
                uvicorn.Config(rt.app, host="0.0.0.0", port=port, log_level="info")
            )
            await server.serve()
        else:
            await _wait_forever()
    finally:
        await rt.stop()


def build_app(agent_name: str) -> FastAPI:
    """Build the agent-scoped ASGI app: ``/chat`` (SSE), ``/ws`` (TUI), ``/health``.

    No ``/admin/*`` and no platform dependency — this serves exactly one agent.
    """
    from collections.abc import AsyncGenerator

    from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    from fleetent import user_store
    from fleetent.runtime.loop import run_stream
    from fleetent.tools.plugin_loader import expand_plugin_patterns

    app = FastAPI(title=f"fleetent-agent:{agent_name}")

    class ChatRequest(BaseModel):
        message: str

    def _authenticate(authorization: str = Header(default="")) -> user_store.User:  # noqa: B008
        token = authorization.removeprefix("Bearer ").strip()
        result = user_store.authenticate(token) if authorization.startswith("Bearer ") else None
        if result is None:
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")
        return result[0]

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "agent": agent_name}

    @app.post("/chat")
    async def chat(
        req: ChatRequest,
        user: user_store.User = Depends(_authenticate),  # noqa: B008
    ) -> StreamingResponse:
        agent = agent_config.current().get(agent_name)
        kwargs: dict[str, Any] = {"user_id": user.id, "agent_name": agent_name}
        if agent is not None:
            kwargs["system_prompt"] = agent.system_prompt
            kwargs["allowed_tools"] = agent.allowed_tools + expand_plugin_patterns(agent.plugins)
            kwargs["agent_features"] = agent.features
            kwargs["allowed_skills"] = agent.allowed_skills

        async def _stream() -> AsyncGenerator[str, None]:
            try:
                async for event in run_stream(req.message, **kwargs):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001 — surface as a stream error, not a 500
                err = {"type": "error", "content": str(exc)}
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @app.websocket("/ws")
    async def ws_gateway(websocket: WebSocket) -> None:
        from fleetent.tui import dispatch as tui_dispatch
        from fleetent.tui import protocol as tui_proto
        from fleetent.tui.transport import WSTransport

        auth = websocket.headers.get("authorization", "")
        result = (
            user_store.authenticate(auth.removeprefix("Bearer ").strip())
            if auth.startswith("Bearer ")
            else None
        )
        if result is None:
            await websocket.close(code=1008)
            return
        user, _ = result
        await websocket.accept()
        transport = WSTransport(websocket)
        conn = tui_dispatch.Connection(user_id=user.id, transport=transport)
        await transport.write(tui_proto.make_event(tui_proto.EVENT_GATEWAY_READY, {}))
        try:
            while True:
                line = await websocket.receive_text()
                try:
                    request = tui_proto.decode_frame(line)
                except tui_proto.ParseError as exc:
                    await transport.write(
                        tui_proto.make_error(None, tui_proto.PARSE_ERROR, str(exc))
                    )
                    continue
                response = await tui_dispatch.dispatch(conn, request)
                if response is not None:
                    await transport.write(response)
        except WebSocketDisconnect:
            pass
        finally:
            conn.cancel_all()
            await transport.close()

    return app
