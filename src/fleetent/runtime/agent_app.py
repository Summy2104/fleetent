"""Single-agent runtime process used by node and local dev/test.

`fleetent agent run <agent-id>` loads a single agent home (`agent.yaml` + `.env` +
`data/` + local access), runs the agent loop, and brings up that agent's IM connectors.
Node uses this as the process primitive for managed deployments; developers may also run
it directly for dev/test. Reuses the shared runtime libs (loop/run_stream, agent_config,
session, MCP, sandbox, the per-agent Slack supervisor) but as an agent-scoped runtime,
not the platform app (see openspec change ``agent-runtime-cli``). HTTP `/chat` + `/ws`
are served only when a port is given.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import signal
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fleetent import agent_config, paths
from fleetent.agent_config import AgentFile
from fleetent.identity import (
    INGRESS_PRINCIPAL_HEADER,
    LocalBearerAdapter,
    Principal,
    decode_ingress_principal,
)
from fleetent.structured_logging import get_logger

if TYPE_CHECKING:
    from fleetent.im_gateway.slack_supervisor import SlackSupervisor
    from fleetent.im_gateway.telegram_supervisor import TelegramSupervisor

_logger = get_logger("runtime.agent_app")


class ChatRequest(BaseModel):
    message: str


class ApprovalRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    approver_user_id: str = "anonymous"


class ImAttachmentRequest(BaseModel):
    kind: str
    data_b64: str | None = None
    mime: str
    filename: str = ""
    note: str = ""


class ImSessionContextRequest(BaseModel):
    platform: str
    sender_id: str
    sender_name: str = ""
    chat_type: str = "dm"
    channel_name: str = ""
    was_mentioned: bool = False
    thread_root: str = ""


class ImRouteRequest(BaseModel):
    platform: str
    session_id: str
    user_id: str
    text: str
    channel_id: str = ""
    workspace_id: str = ""
    agent_name: str = ""
    session_context: ImSessionContextRequest | None = None
    attachments: list[ImAttachmentRequest] = []


class ImReply(BaseModel):
    text: str
    blocks: list[dict[str, Any]] | None = None


class ImRouteResponse(BaseModel):
    replies: list[ImReply]


@dataclass
class AgentRuntime:
    """Handle for one running agent process: its definition, IM supervisor, app."""

    agent: AgentFile
    supervisor: SlackSupervisor
    telegram_supervisor: TelegramSupervisor | None = None
    app: FastAPI | None = None
    port: int | None = None
    scheduler: Any = None

    async def stop(self) -> None:
        # Input shutdown only (stop accepting new work). MCP sessions are released later,
        # after in-flight runs drain (see _drain_and_close) — runs may still use MCP tools.
        # Each step is contained so one failing component never blocks the others.
        await _stop_step("slack_supervisor", self.supervisor.stop_all())
        if self.telegram_supervisor is not None:
            await _stop_step("telegram_supervisor", self.telegram_supervisor.stop_all())
        if self.scheduler is not None:
            await _stop_step("scheduler", self.scheduler.shutdown())
        from fleetent.reflection import scheduler as reflection_scheduler

        await _stop_step("reflection_scheduler", reflection_scheduler.stop_reflection_scheduler())


async def _stop_step(name: str, coro: Awaitable[None], timeout: float = 10.0) -> None:
    """Run one shutdown step under containment: bounded by ``timeout`` and isolated.

    A failing or hanging component is logged and skipped so the remaining steps still run
    and the process exit code is unaffected — graceful shutdown must exit 0 even when a
    component's teardown errors (2026-06-11 MCP teardown crash).
    """
    try:
        await asyncio.wait_for(coro, timeout)
    except Exception as exc:  # noqa: BLE001 — containment: a teardown error never propagates
        _logger.warn("shutdown_step_failed", step=name, error=str(exc))


async def _drain_and_close(rt: AgentRuntime, drain_timeout: float) -> None:
    """Graceful drain chain: stop input → wait for in-flight runs → release MCP sessions.

    MCP sessions close only after the drain so in-flight runs can still use MCP tools;
    the release is contained so a stuck/erroring connector cannot change the exit path.
    """
    from fleetent.integrations import mcp
    from fleetent.runtime import loop as _loop

    _logger.info("agent_drain_started", active_runs=_loop._active_runs, drain_timeout=drain_timeout)
    await rt.stop()
    deadline = asyncio.get_event_loop().time() + drain_timeout
    while _loop._active_runs > 0 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.1)
    if _loop._active_runs > 0:
        _logger.warn("agent_drain_timed_out", active_runs_remaining=_loop._active_runs)
    else:
        _logger.info("agent_drain_completed")
    await _stop_step("mcp_sessions", mcp.aclose_all())


def resolve_home(agent_id: str, home: str | Path | None = None) -> Path:
    """Resolve the agent home: explicit ``home`` wins, else default-tenant home."""
    if home is not None:
        return Path(home)
    return paths.agent_home_dir(agent_id)


def _validate_tui_token(authorization_header: str) -> Principal | None:
    """Check Bearer token against FLEETENT_TUI_TOKEN env var.

    Returns a local Principal on match, None when the token is missing/wrong or the
    env var is not set — so the /ws endpoint can reject without platform user_store access.
    """
    expected = os.environ.get("FLEETENT_TUI_TOKEN", "")
    if not expected:
        return None
    if not authorization_header.startswith("Bearer "):
        return None
    if authorization_header.removeprefix("Bearer ").strip() != expected:
        return None
    return Principal(user_id="local", tenant_id="default")


def _check_tenant(principal: Principal, agent_tenant: str) -> bool:
    """Return True when the Principal's tenant matches the agent's deployment tenant.

    When agent_tenant is 'default' (single-tenant standalone), all callers are allowed.
    In multi-tenant deployments, the principal must belong to the same tenant.
    """
    if agent_tenant == "default":
        return True
    return principal.tenant_id == agent_tenant


def _resolve_ingress_principal(
    authorization_header: str,
    carried_principal_header: str | None,
    *,
    local_bearer: LocalBearerAdapter | None = None,
) -> Principal:
    """Resolve the effective ingress Principal inside the trusted transport boundary."""
    principal = None
    if authorization_header.startswith("Bearer "):
        token = authorization_header.removeprefix("Bearer ").strip()
        adapter = local_bearer or LocalBearerAdapter()
        principal = adapter(token) or _validate_tui_token(authorization_header)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
    try:
        carried_principal = decode_ingress_principal(carried_principal_header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return carried_principal or principal


def _redirect_agent_data_paths(home_dir: Path) -> None:
    """Redirect all per-agent runtime data sinks to ``home_dir/data/``.

    Called once per agent-process boot before any infra initialisation. Assigns
    directly to module-level constants so the change takes effect for all subsequent
    operations in this process without introducing new env vars.
    """
    from fleetent import eval_logger
    from fleetent.im_gateway import access
    from fleetent.integrations.sandbox import manager as sandbox_manager
    from fleetent.integrations.sandbox import output_spill
    from fleetent.observability import diagnostics
    from fleetent.session import manager as session_mgr
    from fleetent.tools import result_truncation

    data_dir = home_dir / "data"
    session_mgr.SESSIONS_DIR = data_dir / "sessions"
    access.APPROVALS_PATH = data_dir / "im_approvals.json"
    eval_logger.TRACE_PATH = data_dir / "traces.jsonl"
    sandbox_manager.set_workspace_root(data_dir / "workspaces")
    result_truncation.SPILLOVER_DIR = data_dir / "tool_spillover"
    output_spill.SANDBOX_OUTPUT_DIR = data_dir / "sandbox_output"
    # Replace the _default_data_dir callable so diagnostics export/retention
    # resolve to this agent's data dir, not the global FLEETENT_HOME/data/.
    diagnostics._default_data_dir = lambda: data_dir  # type: ignore[assignment]


def _configure_logging_from_agent(agent: AgentFile, home_dir: Path) -> None:
    """Apply agent.yaml log_format and observability.logging.* to the runtime logging system.

    Called once per agent process after the agent file is loaded. The platform
    server path (server.py) continues to use configure_logging(Settings) unchanged.
    A blank ``directory`` resolves to ``home_dir/data/logs/``; a relative ``directory``
    resolves against ``home_dir`` (anchored like agent.yaml/.env, never the process CWD);
    an absolute ``directory`` is used as-is.
    """
    import logging

    import structlog

    from fleetent.structured_logging import configure_structured_logging

    log = agent.observability.logging
    if log.directory:
        configured = Path(log.directory)
        resolved_dir = configured if configured.is_absolute() else home_dir / configured
    else:
        resolved_dir = home_dir / "data" / "logs"
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


def _tenant_router_root_for_agent_data_dir(
    data_dir: Path, *, agent_id: str, tenant_id: str
) -> Path:
    """Return Fleetent home root for a tenant-first agent ``data/`` directory.

    Tests and a few direct helpers still pass ``<home>/data`` where ``home`` is not a
    tenant-first path. In that legacy shape, keep the previous "parent is root" behavior.
    """
    agent_home = data_dir.parent
    if (
        data_dir.name == "data"
        and agent_home.name == agent_id
        and agent_home.parent.name == "agents"
        and agent_home.parent.parent.name == tenant_id
        and agent_home.parent.parent.parent.name == "tenants"
    ):
        return agent_home.parent.parent.parent.parent
    return data_dir.parent


def _init_agent_db_schema(data_dir: Path, *, agent_id: str, tenant_id: str = "default") -> None:
    """Bootstrap all agent-side DB tables anchored on data_dir.

    All per-agent tables land in agent_state.db via the unified AGENT_STATE_MIGRATIONS;
    KB and shared-memory tables land in tenant-scoped files via TenantRouter.
    Does not create fleetent.db; does not read DATABASE_URL.
    """
    from fleetent import reflection, schedule_store
    from fleetent.governance import approval_request_store, approval_store
    from fleetent.governance import tool_auto_approvals_store as allowlist_store
    from fleetent.im_gateway import outbound_queue_store
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.memory import agent_memory as agent_memory_module
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces
    from fleetent.runtime import context as runtime_context
    from fleetent.runtime import sub_agent_lifecycle
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.session import index as session_index
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    # Callers pass the running agent's ``<home>/data`` directory. TenantRouter needs the
    # enclosing Fleetent home root; otherwise a tenant-first home would get nested under
    # ``<agent-home>/tenants/...`` at real node runtime.
    router = TenantRouter(
        SQLiteTenantBackend(
            data_dir=_tenant_router_root_for_agent_data_dir(
                data_dir, agent_id=agent_id, tenant_id=tenant_id
            )
        )
    )
    tenant_scope = router.tenant_scope(tenant_id)
    kb_db = tenant_scope.open_kb_db(KB_MIGRATIONS)
    kb_runtime.set_database(kb_db)
    kb_runtime.set_vector_backend(tenant_scope.kb_vector_backend)
    agent_scope = router.agent_scope(tenant_id, agent_id)
    agent_state_db = agent_scope.open_state_db(AGENT_STATE_MIGRATIONS)
    # agent_memory_items now live in agent_state.db (wire-agent-memory D3).
    agent_memory_module.set_agent_memory_db(
        agent_state_db,
        agent_scope.vector_backend,
    )
    session_index.set_state_db(agent_state_db)
    traces.set_state_db(agent_state_db)
    reflection.set_state_db(agent_state_db)
    memory_store.set_state_db(agent_state_db)
    memory_store.set_vector_backend(agent_scope.vector_backend)
    approval_request_store.set_state_db(agent_state_db)
    approval_store.set_state_db(agent_state_db)
    allowlist_store.set_state_db(agent_state_db)
    runtime_context.set_state_db(agent_state_db)
    sub_agent_lifecycle.set_state_db(agent_state_db)
    schedule_store.set_state_db(agent_state_db)
    outbound_queue_store.set_state_db(agent_state_db)
    # unified-file-exchange: wire the artifact ledger + per-scope hard-link views root
    # (data_dir is <agent_home>/data, so the exchange tree lives under data_dir.parent).
    from fleetent import artifact_exchange

    artifact_exchange.set_state_db(agent_state_db)
    artifact_exchange.set_views_root(data_dir.parent / "exchange" / ".views")


async def _start_infra(
    agent: AgentFile, data_dir: Path, *, skills_root: Path | None = None
) -> None:
    """Best-effort process infrastructure: sandbox probe, per-agent MCP, session upkeep.

    Each step mirrors the platform lifespan but scoped to this one agent; a failure is
    logged and never aborts boot (same best-effort posture as the platform).

    `skills_root` is this agent's per-agent skills root (the same `home_dir/skills`
    boot scans the skill index from); it seeds the sandbox skill-mount source default so
    the container's `/workspace/skills` matches the scan root
    (sandbox-skill-mount-per-agent-root). None derives it from `data_dir.parent`
    (== home_dir, mirroring the MCP `agent_home` derivation below).
    """
    _init_agent_db_schema(data_dir, agent_id=agent.name, tenant_id=agent.tenant_id)
    from fleetent.runtime.approval_resume import reconcile_expired_approvals

    await reconcile_expired_approvals()
    from fleetent.integrations.sandbox import enablement as sandbox_enablement

    # Select the configured sandbox backend (agent.yaml > platform.yaml > docker) and
    # build the process sandbox manager around it so run_code uses the right backend.
    from fleetent.integrations.sandbox.factory import create_backend
    from fleetent.session import manager as session_mgr
    from fleetent.tools.builtin_tools import init_sandbox_manager

    backend = create_backend(agent)
    init_sandbox_manager(agent, agent_skills_root=skills_root or (data_dir.parent / "skills"))

    mode = await sandbox_enablement.get_effective_mode(backend)  # one-time probe, cached
    # sandbox-runtime-lifecycle-wiring: only when the backend is usable (effective mode
    # != off) do we reap last-run orphan workspaces and schedule agent-scope idle
    # reclamation. Orphan cleanup is best-effort (a failure is logged, never aborts
    # boot) and capability-gated; the idle sweep is a bare-asyncio loop mirroring
    # session maintenance.
    if mode is not sandbox_enablement.Mode.OFF:
        from fleetent.integrations.sandbox import cleanup_orphans, start_idle_sweep

        try:
            await cleanup_orphans(backend)
        except Exception as exc:  # noqa: BLE001 — orphan cleanup must not abort boot
            _logger.warn("agent_runtime_sandbox_cleanup_failed", error=str(exc))
        start_idle_sweep()
    if agent.mcp_servers:
        from fleetent.integrations import mcp as mcp_client
        from fleetent.integrations.mcp.client import McpServerConfig

        configs = [McpServerConfig.from_settings(s) for s in agent.mcp_servers]
        try:
            # unified-file-exchange: the agent home (data_dir's parent) anchors each
            # stdio server's /exchange partition tree (cwd + XDG injection + root binding).
            await mcp_client.register_all(
                configs, agent_home=data_dir.parent, tool_naming=agent.mcp.tool_naming
            )
        except Exception as exc:  # noqa: BLE001 — MCP unavailable must not abort boot
            _logger.warn("agent_runtime_mcp_register_failed", error=str(exc))
    session_mgr.start_session_maintenance()
    reflection_settings = getattr(agent, "reflection", None)
    if reflection_settings is not None and getattr(reflection_settings, "enabled", False) is True:
        from fleetent.reflection import scheduler as reflection_scheduler
        from fleetent.reflection.reflection import AutoMaintenancePolicy

        auto_policy = AutoMaintenancePolicy(
            allow_low_risk=reflection_settings.auto_apply.allow_low_risk
        )

        reflection_scheduler.start_reflection_scheduler(
            interval=reflection_settings.interval_seconds,
            scope=agent.name,
            auto_policy=auto_policy,
        )
    # Restart recovery: flag sessions active just before this (re)start so the next
    # request can be recognized as a resumed conversation. Best-effort — a scan
    # failure must never abort boot.
    try:
        marked = session_mgr.scan_and_mark_recent_resume()
        if marked:
            _logger.info("session_resume_pending_marked", count=len(marked))
    except Exception as exc:  # noqa: BLE001 — recovery scan must not abort boot
        _logger.warn("session_resume_scan_failed", error=str(exc))


async def _start_scheduler(agent: AgentFile) -> Any:
    """Start this agent's CronScheduler (agent-owned-scheduled-tasks), or None if disabled.

    Delivery connectors are resolved at fire time from the per-process connector
    registry the IM adapters populate, so a task fired after a connector connects (or
    reconnects) still reaches the user.
    """
    if not agent.scheduling.enabled:
        return None
    from fleetent.cron_scheduler import CronScheduler
    from fleetent.im_gateway import connector_registry
    from fleetent.outbound_connectors import resolve_for_runtime

    agent_name = agent.name
    scheduler = CronScheduler(
        settings=agent.scheduling,
        connectors_resolver=lambda: resolve_for_runtime(
            agent_name, connector_registry.snapshot(agent_name)
        ),
    )
    await scheduler.start()
    return scheduler


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
    # a missing dir scans to builtin-only (skill-nested-scan safe). The same per-agent
    # root seeds the sandbox skill-mount default so the container's /workspace/skills ==
    # this scan root (sandbox-skill-mount-per-agent-root).
    skills_root = home_dir / "skills"
    scan_skills(skills_dir=str(skills_root))
    load_plugins()

    if with_infra:
        await _start_infra(agent, home_dir / "data", skills_root=skills_root)

    if supervisor is None:
        from fleetent.im_gateway.slack_supervisor import SlackSupervisor

        supervisor = SlackSupervisor()
    if telegram_supervisor is None:
        from fleetent.im_gateway.telegram_supervisor import TelegramSupervisor

        telegram_supervisor = TelegramSupervisor()
    if start_im:
        await supervisor.start(agent.name)
        await telegram_supervisor.start(agent.name)

    scheduler = await _start_scheduler(agent) if with_infra else None

    app = build_app(agent.name) if port is not None else None
    _logger.info("agent_runtime_booted", agent=agent.name, http_port=port, im=start_im)
    return AgentRuntime(
        agent=agent,
        supervisor=supervisor,
        telegram_supervisor=telegram_supervisor,
        app=app,
        port=port,
        scheduler=scheduler,
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
    start_im: bool = True,
) -> None:
    """Boot the agent and run it in the foreground until cancelled or drained.

    With ``port`` the agent app is served over HTTP (``/chat`` + ``/ws``); without it the
    process runs IM-only with no HTTP listener. On SIGUSR1 the process drains in-flight
    requests (up to drain_timeout) then exits.
    """
    home_dir = resolve_home(agent_id, home)
    home_dir.mkdir(parents=True, exist_ok=True)
    pid_file = home_dir / ".fleetent.pid"
    pid_file.write_text(str(os.getpid()))

    drain_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGUSR1, drain_event.set)

    try:
        rt = await boot(agent_id, home=home, port=port, start_im=start_im)
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
            await _drain_and_close(rt, drain_timeout)
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

    _local_bearer = LocalBearerAdapter()

    def _authenticate(
        authorization: str = Header(default=""),  # noqa: B008
        carried_principal_header: str | None = Header(  # noqa: B008
            default=None, alias=INGRESS_PRINCIPAL_HEADER
        ),
    ) -> Principal:
        return _resolve_ingress_principal(
            authorization,
            carried_principal_header,
            local_bearer=_local_bearer,
        )

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
        from fleetent.governance.approval_router import resolve_approval_request

        if req.decision not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
        found = await resolve_approval_request(
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
        principal: Principal = Depends(_authenticate),  # noqa: B008
    ) -> StreamingResponse:
        agent = agent_config.current().get(agent_name)
        agent_tenant = agent.tenant_id if agent is not None else "default"
        if not _check_tenant(principal, agent_tenant):
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        kwargs: dict[str, Any] = {"principal": principal, "agent_name": agent_name}
        if agent is not None:
            kwargs["system_prompt"] = agent.system_prompt
            kwargs["allowed_tools"] = (
                agent.allowed_tools + expand_plugin_patterns(agent.plugins)
            ) or None
            kwargs["agent_features"] = agent.features
            kwargs["allowed_skills"] = agent.allowed_skills
            kwargs["skill_authoring_enabled"] = agent.skill_authoring_enabled
            kwargs["skill_hot_reload"] = agent.skill_hot_reload
            kwargs["skill_user_access"] = agent.skill_user_access
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

    @app.post("/im/route")
    async def im_route(
        req: ImRouteRequest,
        principal: Principal = Depends(_authenticate),  # noqa: B008
    ) -> ImRouteResponse:
        from fleetent.im_gateway import normalizer

        agent = agent_config.current().get(agent_name)
        agent_tenant = agent.tenant_id if agent is not None else "default"
        if not _check_tenant(principal, agent_tenant):
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        replies: list[ImReply] = []

        async def _reply(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
            replies.append(ImReply(text=text, blocks=blocks))

        await normalizer.route(
            normalizer.NormalizedMessage(
                platform=req.platform,
                session_id=req.session_id,
                user_id=req.user_id,
                text=req.text,
                attachments=_deserialize_im_attachments(req.attachments),
                reply_func=_reply,
                channel_id=req.channel_id,
                workspace_id=req.workspace_id,
                agent_name=req.agent_name or agent_name,
                session_context=(
                    normalizer.SessionContext(**req.session_context.model_dump())
                    if req.session_context is not None
                    else None
                ),
            ),
            principal=principal,
        )
        return ImRouteResponse(replies=replies)

    @app.websocket("/ws")
    async def ws_gateway(websocket: WebSocket) -> None:
        from fleetent.tui import dispatch as tui_dispatch
        from fleetent.tui import protocol as tui_proto
        from fleetent.tui.transport import WSTransport

        auth = websocket.headers.get("authorization", "")
        tui_principal = _validate_tui_token(auth)
        if tui_principal is None:
            # No FLEETENT_TUI_TOKEN configured or token mismatch.
            # Run `fleetent agent init --force` or add FLEETENT_TUI_TOKEN to .env.
            _logger.warn(
                "tui_ws_auth_rejected",
                hint="Set FLEETENT_TUI_TOKEN in agent .env; run: fleetent agent init --force",
            )
            await websocket.close(code=1008)
            return
        try:
            principal = decode_ingress_principal(
                websocket.headers.get(INGRESS_PRINCIPAL_HEADER.lower())
            )
        except ValueError:
            await websocket.close(code=1008)
            return
        effective_principal = principal or tui_principal
        agent = agent_config.current().get(agent_name)
        agent_tenant = agent.tenant_id if agent is not None else "default"
        if not _check_tenant(effective_principal, agent_tenant):
            _logger.warn("tui_ws_cross_tenant_rejected", agent_tenant=agent_tenant)
            await websocket.close(code=1008)
            return
        await websocket.accept()
        transport = WSTransport(websocket)
        conn = tui_dispatch.Connection(
            principal=effective_principal, transport=transport, agent_name=agent_name
        )
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


def _deserialize_im_attachments(attachments: list[ImAttachmentRequest]) -> list[Any]:
    from fleetent.im_gateway.normalizer import FileAttachment

    decoded: list[Any] = []
    for attachment in attachments:
        if attachment.kind == "image":
            if attachment.data_b64 is None:
                continue
            decoded.append((base64.b64decode(attachment.data_b64), attachment.mime))
            continue
        if attachment.kind == "file":
            payload = base64.b64decode(attachment.data_b64) if attachment.data_b64 else None
            decoded.append(
                FileAttachment(
                    data=payload,
                    mime=attachment.mime,
                    filename=attachment.filename,
                    note=attachment.note,
                )
            )
    return decoded
