"""Standalone agent runtime: boot one agent home as a self-contained process.

`fleetent agent run <agent-id>` loads a single agent home (`agent.yaml` + `.env` +
`data/` + local access), runs the agent loop, and brings up that agent's IM connectors —
with no platform service. Reuses the shared runtime libs (loop/run_stream, agent_config,
session, MCP, sandbox, the per-agent Slack supervisor) but as an agent-scoped runtime,
not the platform app (see openspec change ``agent-runtime-cli``). HTTP `/chat` + `/ws`
are served only when a port is given.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fleetent import agent_config, paths, user_store
from fleetent.agent_config import AgentFile
from fleetent.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from fleetent.im_gateway.slack_supervisor import SlackSupervisor
    from fleetent.im_gateway.telegram_supervisor import TelegramSupervisor

_logger = get_logger("runtime.agent_app")


class ChatRequest(BaseModel):
    message: str


class ApprovalRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    approver_user_id: str = "anonymous"


@dataclass
class AgentRuntime:
    """Handle for a running standalone agent: its definition, IM supervisor, app."""

    agent: AgentFile
    supervisor: SlackSupervisor
    telegram_supervisor: TelegramSupervisor | None = None
    app: FastAPI | None = None
    port: int | None = None

    async def stop(self) -> None:
        await self.supervisor.stop_all()
        if self.telegram_supervisor is not None:
            await self.telegram_supervisor.stop_all()


def resolve_home(agent_id: str, home: str | Path | None = None) -> Path:
    """Resolve the agent home: explicit ``home`` wins, else ``FLEETENT_HOME/agents/<id>``."""
    if home is not None:
        return Path(home)
    return paths.base_dir() / "agents" / agent_id


def _validate_tui_token(authorization_header: str) -> bool:
    """Check Bearer token against FLEETENT_TUI_TOKEN env var.

    Returns False when the token is missing/wrong OR when the env var is not set,
    so the /ws endpoint can reject connections without platform user_store access.
    """
    expected = os.environ.get("FLEETENT_TUI_TOKEN", "")
    if not expected:
        return False
    if not authorization_header.startswith("Bearer "):
        return False
    return authorization_header.removeprefix("Bearer ").strip() == expected


def _redirect_agent_data_paths(home_dir: Path) -> None:
    """Redirect all per-agent runtime data sinks to ``home_dir/data/``.

    Called once per standalone agent boot before any infra initialisation. Assigns
    directly to module-level constants so the change takes effect for all subsequent
    operations in this process without introducing new env vars.
    """
    from fleetent.im_gateway import access
    from fleetent.observability import diagnostics
    from fleetent.session import manager as session_mgr

    data_dir = home_dir / "data"
    session_mgr.SESSIONS_DIR = data_dir / "sessions"
    access.APPROVALS_PATH = data_dir / "im_approvals.json"
    # Replace the _default_data_dir callable so diagnostics export/retention
    # resolve to this agent's data dir, not the global FLEETENT_HOME/data/.
    diagnostics._default_data_dir = lambda: data_dir  # type: ignore[assignment]
    # Only set DATABASE_URL if not already configured (explicit .env or system env wins).
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{data_dir / 'fleetent.db'}")


def _configure_logging_from_agent(agent: AgentFile, home_dir: Path) -> None:
    """Apply agent.yaml log_format and observability.logging.* to the runtime logging system.

    Called once per standalone agent process after the agent file is loaded. The platform
    server path (server.py) continues to use configure_logging(Settings) unchanged.
    A blank ``directory`` resolves to ``home_dir/data/logs/`` so log files land per-agent.
    """
    import logging

    import structlog

    from fleetent.observability.structured_logging import configure_structured_logging

    log = agent.observability.logging
    resolved_dir: str | Path = log.directory if log.directory else home_dir / "data" / "logs"
    configure_structured_logging(
        console_level=log.console_level,
        file_level=log.file_level,
        directory=resolved_dir,
    )
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if agent.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )


def _init_agent_db_schema(database_url: str) -> None:
    """Create all agent-side DB tables in database_url if they do not exist.

    Called once at boot after DATABASE_URL is redirected to the per-agent path.
    Each store's ensure_schema is idempotent; repeated calls are safe.
    """
    from fleetent import reflection
    from fleetent.db import create_database
    from fleetent.knowledge_base import operations as kb_ops
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces

    db = create_database(database_url)
    traces.ensure_schema(db)
    memory_store.ensure_schema(db)
    reflection.ensure_schema(db)
    kb_ops.ensure_schema(db)


async def _start_infra(agent: AgentFile) -> None:
    """Best-effort process infrastructure: sandbox probe, per-agent MCP, session upkeep.

    Each step mirrors the platform lifespan but scoped to this one agent; a failure is
    logged and never aborts boot (same best-effort posture as the platform).
    """
    _db_url = os.environ.get("DATABASE_URL", "")
    if _db_url:
        _init_agent_db_schema(_db_url)
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    mode = await sandbox_enablement.get_effective_mode()  # one-time Docker probe, cached
    # sandbox-runtime-lifecycle-wiring: only when Docker is usable (effective mode != off)
    # do we reap last-run orphan containers and schedule agent-scope idle reclamation.
    # Orphan cleanup is best-effort (a failure is logged, never aborts boot); the idle
    # sweep is a bare-asyncio loop mirroring session maintenance.
    if mode is not sandbox_enablement.Mode.OFF:
        from fleetent.integrations.sandbox import (
            SandboxClient,
            cleanup_orphans,
            start_idle_sweep,
        )

        try:
            await cleanup_orphans(SandboxClient())
        except Exception as exc:  # noqa: BLE001 — orphan cleanup must not abort boot
            _logger.warn("agent_runtime_sandbox_cleanup_failed", error=str(exc))
        start_idle_sweep()
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
                connect_timeout=s.connect_timeout,
                call_timeout=s.call_timeout,
            )
            for s in agent.mcp_servers
        ]
        try:
            await mcp_client.register_all(configs)
        except Exception as exc:  # noqa: BLE001 — MCP unavailable must not abort boot
            _logger.warn("agent_runtime_mcp_register_failed", error=str(exc))
    session_mgr.start_session_maintenance()
    # Restart recovery: flag sessions active just before this (re)start so the next
    # request can be recognized as a resumed conversation. Best-effort — a scan
    # failure must never abort boot.
    try:
        marked = session_mgr.scan_and_mark_recent_resume()
        if marked:
            _logger.info("session_resume_pending_marked", count=len(marked))
    except Exception as exc:  # noqa: BLE001 — recovery scan must not abort boot
        _logger.warn("session_resume_scan_failed", error=str(exc))


async def boot(
    agent_id: str,
    *,
    home: str | Path | None = None,
    port: int | None = None,
    supervisor: SlackSupervisor | None = None,
    telegram_supervisor: TelegramSupervisor | None = None,
    start_im: bool = True,
    with_infra: bool = True,
) -> AgentRuntime:
    """Boot a single self-contained agent: load its home, bind IM, optionally serve HTTP.

    Publishes a single-agent index so routing resolves only this agent. Starts the agent's
    per-agent IM connectors (Slack + Telegram) from its home schema. With ``port``, builds
    the agent app serving ``/chat`` + ``/ws``.
    """
    from fleetent.skills import scan as scan_skills
    from fleetent.tools.plugin_loader import load_plugins

    home_dir = resolve_home(agent_id, home)
    env_path = home_dir / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    _redirect_agent_data_paths(home_dir)
    agent = agent_config.scan_home(home_dir)
    _configure_logging_from_agent(agent, home_dir)
    # Re-point the vector/embedding singletons at this agent's intelligence config
    # (import-time config used global Settings; standalone runs AS this single agent).
    from fleetent import vector_store

    vector_store.configure_from_active_agent()
    # Build this agent's skill index from its OWN home (self-contained: never the
    # process CWD or FLEETENT_SKILLS_DIR). materialize copies skill files to home/skills/;
    # a missing dir scans to builtin-only (skill-nested-scan safe).
    scan_skills(skills_dir=str(home_dir / "skills"))
    load_plugins()

    if with_infra:
        await _start_infra(agent)

    if supervisor is None:
        from fleetent.im_gateway.slack_supervisor import SlackSupervisor

        supervisor = SlackSupervisor()
    if telegram_supervisor is None:
        from fleetent.im_gateway.telegram_supervisor import TelegramSupervisor

        telegram_supervisor = TelegramSupervisor()
    if start_im:
        await supervisor.start(agent.name)
        await telegram_supervisor.start(agent.name)

    app = build_app(agent.name) if port is not None else None
    _logger.info("agent_runtime_booted", agent=agent.name, http_port=port, im=start_im)
    return AgentRuntime(
        agent=agent,
        supervisor=supervisor,
        telegram_supervisor=telegram_supervisor,
        app=app,
        port=port,
    )


def _sleep(seconds: float) -> None:
    """Thin wrapper around time.sleep, injectable in tests."""
    time.sleep(seconds)


async def _wait_forever() -> None:
    """Block until cancelled (IM-only foreground runtime has no HTTP server to await)."""
    await asyncio.Event().wait()


def _stop_running(home_dir: Path, *, drain_timeout: float = 30.0) -> None:
    """Send SIGUSR1 to the PID in ``home_dir/.fleetent.pid`` and wait for graceful exit.

    Falls back to SIGTERM after drain_timeout, then SIGKILL after 5 more seconds.
    Silently succeeds if no pid file exists or the process is already gone.
    """
    pid_file = home_dir / ".fleetent.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return

    # Phase 1: SIGUSR1 → graceful drain
    try:
        os.kill(pid, signal.SIGUSR1)
        _logger.info("agent_drain_requested", pid=pid, drain_timeout=drain_timeout)
    except ProcessLookupError:
        _logger.debug("agent_process_already_gone", pid=pid, phase="sigusr1")
        pid_file.unlink(missing_ok=True)
        return

    deadline = time.monotonic() + drain_timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            _sleep(0.05)
        except ProcessLookupError:
            _logger.debug("agent_process_exited_gracefully", pid=pid)
            pid_file.unlink(missing_ok=True)
            return

    # Phase 2: SIGTERM fallback
    _logger.warn("agent_drain_timeout", pid=pid, drain_timeout=drain_timeout)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            _sleep(0.05)
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)
            return

    # Phase 3: SIGKILL
    _logger.warn("agent_force_kill", pid=pid)
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    pid_file.unlink(missing_ok=True)


async def serve(
    agent_id: str,
    *,
    port: int | None = None,
    home: str | Path | None = None,
    drain_timeout: float = 30.0,
) -> None:
    """Boot the agent and run it in the foreground until cancelled or drained.

    With ``port`` the agent app is served over HTTP (``/chat`` + ``/ws``); without it the
    process runs IM-only with no HTTP listener. On SIGUSR1 the process drains in-flight
    requests (up to drain_timeout) then exits.
    """
    from fleetent.runtime import loop as _loop

    home_dir = resolve_home(agent_id, home)
    home_dir.mkdir(parents=True, exist_ok=True)
    pid_file = home_dir / ".fleetent.pid"
    pid_file.write_text(str(os.getpid()))

    drain_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGUSR1, drain_event.set)

    async def _drain_and_exit(rt: AgentRuntime) -> None:
        _logger.info(
            "agent_drain_started", active_runs=_loop._active_runs, drain_timeout=drain_timeout
        )  # noqa: E501
        await rt.stop()
        deadline = asyncio.get_event_loop().time() + drain_timeout
        while _loop._active_runs > 0 and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
        if _loop._active_runs > 0:
            _logger.warn("agent_drain_timed_out", active_runs_remaining=_loop._active_runs)
        else:
            _logger.info("agent_drain_completed")

    try:
        rt = await boot(agent_id, home=home, port=port)
        try:
            if port is not None:
                import uvicorn

                assert rt.app is not None
                server = uvicorn.Server(
                    uvicorn.Config(rt.app, host="0.0.0.0", port=port, log_level="info")
                )
                drain_task = asyncio.ensure_future(drain_event.wait())
                serve_task = asyncio.ensure_future(server.serve())
                done, _ = await asyncio.wait(
                    [drain_task, serve_task], return_when=asyncio.FIRST_COMPLETED
                )
                if drain_task in done:
                    server.should_exit = True
                    await serve_task
                serve_task.cancel()
                drain_task.cancel()
            else:
                wait_task = asyncio.ensure_future(_wait_forever())
                drain_task = asyncio.ensure_future(drain_event.wait())
                await asyncio.wait([wait_task, drain_task], return_when=asyncio.FIRST_COMPLETED)
                wait_task.cancel()
                drain_task.cancel()
        finally:
            await _drain_and_exit(rt)
    finally:
        loop.remove_signal_handler(signal.SIGUSR1)
        pid_file.unlink(missing_ok=True)


def build_app(agent_name: str) -> FastAPI:
    """Build the agent-scoped ASGI app: ``/chat`` (SSE), ``/ws`` (TUI), ``/health``.

    No ``/admin/*`` and no platform dependency — this serves exactly one agent.
    """
    from collections.abc import AsyncGenerator

    from fleetent.model import ModelPolicySnapshot
    from fleetent.runtime.loop import run_stream
    from fleetent.runtime.snapshot import _governance_from_file
    from fleetent.tools.plugin_loader import expand_plugin_patterns

    app = FastAPI(title=f"fleetent-agent:{agent_name}")

    def _authenticate(authorization: str = Header(default="")) -> user_store.User:  # noqa: B008
        token = authorization.removeprefix("Bearer ").strip()
        result = user_store.authenticate(token) if authorization.startswith("Bearer ") else None
        if result is None:
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")
        return result[0]

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "agent": agent_name}

    # Approval endpoints: allow medium/high-risk tool calls to be approved without
    # requiring the full platform server. Standalone agents need these so that IM
    # users can unblock pending tool approvals via the /chat WebSocket or external
    # tooling.
    @app.get("/approvals")
    async def get_approvals(status: str | None = None) -> list:  # type: ignore[type-arg]
        from fleetent.governance.permission_gate import list_approvals

        return list_approvals(status=status)

    @app.post("/approvals/{approval_id}/resolve")
    async def resolve_approval(approval_id: str, req: ApprovalRequest) -> dict:  # type: ignore[type-arg]
        from fleetent.governance.permission_gate import _default_gate

        if req.decision not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
        found = await _default_gate.resolve(
            approval_id=approval_id,
            decision=req.decision,  # type: ignore[arg-type]
            approver_user_id=req.approver_user_id,
        )
        if not found:
            raise HTTPException(
                status_code=404, detail=f"approval {approval_id} not found or expired"
            )
        return {"status": "ok", "approval_id": approval_id, "decision": req.decision}

    @app.post("/chat")
    async def chat(
        req: ChatRequest,
        user: user_store.User = Depends(_authenticate),  # noqa: B008
    ) -> StreamingResponse:
        agent = agent_config.current().get(agent_name)
        kwargs: dict[str, Any] = {"user_id": user.id, "agent_name": agent_name}
        if agent is not None:
            kwargs["system_prompt"] = agent.system_prompt
            kwargs["allowed_tools"] = (
                agent.allowed_tools + expand_plugin_patterns(agent.plugins)
            ) or None
            kwargs["agent_features"] = agent.features
            kwargs["allowed_skills"] = agent.allowed_skills
            kwargs["governance"] = _governance_from_file(agent)
            kwargs["model_policy"] = ModelPolicySnapshot.from_agent(agent)

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
        if not _validate_tui_token(auth):
            # No FLEETENT_TUI_TOKEN configured or token mismatch.
            # Run `fleetent agent init --force` or add FLEETENT_TUI_TOKEN to .env.
            _logger.warning(
                "tui_ws_auth_rejected",
                hint="Set FLEETENT_TUI_TOKEN in agent .env; run: fleetent agent init --force",
            )
            await websocket.close(code=1008)
            return
        await websocket.accept()
        transport = WSTransport(websocket)
        conn = tui_dispatch.Connection(user_id="local", transport=transport)
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
