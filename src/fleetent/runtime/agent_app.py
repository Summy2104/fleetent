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
import contextlib
import json
import os
import signal
import threading
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
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


@dataclass
class AgentRuntime:
    """Handle for one running agent process: its definition, IM supervisor, app."""

    agent: AgentFile
    supervisor: SlackSupervisor
    telegram_supervisor: TelegramSupervisor | None = None
    app: FastAPI | None = None
    port: int | None = None
    scheduler: Any = None
    workflow_engine: Any = None

    async def stop(self) -> None:
        # Input shutdown only (stop accepting new work). MCP sessions are released later,
        # after in-flight runs drain (see _drain_and_close) — runs may still use MCP tools.
        # Each step is contained so one failing component never blocks the others.
        await _stop_step("slack_supervisor", self.supervisor.stop_all())
        if self.telegram_supervisor is not None:
            await _stop_step("telegram_supervisor", self.telegram_supervisor.stop_all())
        if self.scheduler is not None:
            await _stop_step("scheduler", self.scheduler.shutdown())
        if self.workflow_engine is not None:
            await _stop_step("workflow_engine", self.workflow_engine.stop())
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
        _logger.warn("shutdown_step_failed", step=name, exception=exc)


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
    from fleetent.memory import facts_lifecycle

    await _stop_step("facts_archive_sweep", facts_lifecycle.stop_archive_sweep())
    # Stop the per-user stdio reaper before releasing sessions; aclose_all() then tears
    # down every host (incl. per-user stdio subprocesses) on its own owner task (D4).
    await _stop_step("mcp_stdio_reaper", mcp.stop_stdio_reaper())
    await _stop_step("mcp_sessions", mcp.aclose_all())
    # AAA-8204 #4: aclose_all only closes stdin; npm/node/chromium MCP subprocesses (+ their
    # grandchildren) may not exit, leaving 8 waitpid reader threads blocked so the interpreter
    # never exits and node SIGKILLs the agent every restart. Deterministically drive exit:
    # force-kill the descendant process tree (freeing those threads) + arm an os._exit(0)
    # watchdog. The graceful drain path MUST exit 0 (AGENTS.md owner-task contract).
    _drive_exit_after_drain()


# AAA-8204 #4 graceful-exit timings: SIGTERM→grace→SIGKILL for residual MCP subprocess trees,
# then an os._exit(0) fallback if the interpreter still has not exited on its own.
_SUBPROCESS_TERM_GRACE = 2.0
_HARD_EXIT_DEADLINE = 5.0


def _pid_alive(pid: int) -> bool:
    """Whether ``pid`` is still alive (signal 0 probe). False on any OS error."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _list_descendant_pids(pid: int) -> list[int]:
    """All descendant PIDs of ``pid`` (children, grandchildren, …), breadth-first.

    Linux ``/proc`` PPID walk. On a host without a readable ``/proc`` (macOS dev, sandbox)
    this returns ``[]`` — read-only and never raises — and the os._exit watchdog still
    guarantees the process exits. Used at shutdown to reap stdio MCP subprocess trees.
    """
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    children: dict[int, list[int]] = {}
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                content = fh.read()
            # stat is "pid (comm) state ppid ..."; comm may contain spaces/parens, so parse
            # the fields after the LAST ')'. ppid is the second of those fields.
            ppid = int(content[content.rfind(")") + 2 :].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(entry))
    out: list[int] = []
    queue = list(children.get(pid, []))
    while queue:
        cur = queue.pop(0)
        out.append(cur)
        queue.extend(children.get(cur, []))
    return out


def _terminate_descendant_processes(grace: float) -> None:
    """SIGTERM then (after ``grace``) SIGKILL the agent's whole descendant process tree.

    Frees the waitpid reader threads blocked on stdio MCP subprocesses (and their npm/node/
    chromium grandchildren), which otherwise keep the interpreter from exiting. Each signal
    is contained per-PID so one unkillable/permission-denied process never blocks the rest
    or changes the exit path. SIGTERM is sent deepest-first so a parent cannot respawn.
    """
    pids = _list_descendant_pids(os.getpid())
    if not pids:
        return
    for pid in reversed(pids):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not any(_pid_alive(pid) for pid in pids):
            return
        time.sleep(0.05)
    for pid in reversed(pids):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)


def _arm_hard_exit_watchdog(deadline: float) -> None:
    """Arm a daemon timer that ``os._exit(0)`` if the process is still alive after ``deadline``.

    Daemon so the timer itself never keeps the process up: if the interpreter exits cleanly
    first, the timer is reaped with it. This is the last-resort guarantee that a graceful
    drain exits 0 even when some teardown ignored cancellation (AAA-8204 #4).
    """
    timer = threading.Timer(deadline, lambda: os._exit(0))
    timer.daemon = True
    timer.start()


def _drive_exit_after_drain(
    grace: float = _SUBPROCESS_TERM_GRACE, hard_deadline: float = _HARD_EXIT_DEADLINE
) -> None:
    """Deterministically drive process exit after drain (AAA-8204 #4).

    First force-kill the residual MCP subprocess tree (bulkheaded: a failure here is logged,
    never raised, and never blocks the exit), then arm the os._exit(0) watchdog. Together
    these cover both diagnosed causes — lingering non-daemon waitpid threads and a teardown
    that ignored cancellation.
    """
    try:
        _terminate_descendant_processes(grace)
    except Exception as exc:  # noqa: BLE001 — contained: the watchdog still guarantees exit
        _logger.warn("drive_exit_terminate_failed", exception=exc)
    _arm_hard_exit_watchdog(hard_deadline)


def resolve_home(agent_name: str, home: str | Path | None = None) -> Path:
    """Resolve the agent home: explicit ``home`` wins, else default-tenant home."""
    if home is not None:
        return Path(home)
    return paths.agent_home_dir(agent_name)


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
        principal = _validate_tui_token(authorization_header) or adapter(token)
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
    from fleetent.logging_setup import setup_process_logging

    log = agent.observability.logging
    if log.directory:
        configured = Path(log.directory)
        resolved_dir = configured if configured.is_absolute() else home_dir / configured
    else:
        resolved_dir = home_dir / "data" / "logs"
    setup_process_logging(
        console_level=log.console_level,
        file_level=log.file_level,
        directory=resolved_dir,
        log_format=agent.log_format,
    )


def _tenant_router_root_for_agent_data_dir(
    data_dir: Path, *, agent_name: str, tenant_id: str
) -> Path:
    """Return Fleetent home root for a tenant-first agent ``data/`` directory.

    Tests and a few direct helpers still pass ``<home>/data`` where ``home`` is not a
    tenant-first path. In that legacy shape, keep the previous "parent is root" behavior.
    """
    agent_home = data_dir.parent
    if (
        data_dir.name == "data"
        and agent_home.name == agent_name
        and agent_home.parent.name == "agents"
        and agent_home.parent.parent.name == tenant_id
        and agent_home.parent.parent.parent.name == "tenants"
    ):
        return agent_home.parent.parent.parent.parent
    return data_dir.parent


def _resolve_auth_ref(auth_ref: str) -> str:
    if auth_ref.startswith("env:"):
        env_name = auth_ref.removeprefix("env:")
        value = os.getenv(env_name)
        if value:
            return value
        raise ValueError(f"knowledge.provider.auth_ref env var is missing: {env_name}")
    path = Path(auth_ref.removeprefix("file://")).expanduser()
    return path.read_text(encoding="utf-8")


def _configure_knowledge_provider(agent: AgentFile, *, long_term_ctx: Any) -> None:
    knowledge = getattr(agent, "knowledge", None)
    provider = getattr(knowledge, "provider", None)
    if provider is None:
        long_term_ctx.set_knowledge_provider(None)
        return
    if provider.type != "http":
        long_term_ctx.set_knowledge_provider(None)
        return
    long_term_ctx.set_knowledge_provider(
        long_term_ctx.HttpKnowledgeProvider(
            provider.url or "",
            service_key=_resolve_auth_ref(provider.auth_ref or ""),
        )
    )


def _init_agent_db_schema(data_dir: Path, *, agent_name: str, tenant_id: str = "default") -> None:
    """Bootstrap all agent-side DB tables anchored on data_dir.

    All per-agent tables land in agent_state.db via the unified AGENT_STATE_MIGRATIONS;
    KB and shared-memory tables land in tenant-scoped files via TenantRouter.
    Does not create fleetent.db; does not read DATABASE_URL.
    """
    from fleetent import reflection, schedule_store
    from fleetent.governance import approval_request_store, approval_store
    from fleetent.governance import tool_auto_approvals_store as allowlist_store
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.memory import agent_memory as agent_memory_module
    from fleetent.memory import facts_store
    from fleetent.memory import proposal_store as memory_proposal_store
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
                data_dir, agent_name=agent_name, tenant_id=tenant_id
            )
        )
    )
    tenant_scope = router.tenant_scope(tenant_id)
    kb_db = tenant_scope.open_kb_db(KB_MIGRATIONS)
    kb_runtime.set_database(kb_db)
    kb_runtime.set_vector_backend(tenant_scope.kb_vector_backend)
    agent_scope = router.agent_scope(tenant_id, agent_name)
    agent_state_db = agent_scope.open_state_db(AGENT_STATE_MIGRATIONS)
    # agent_memory_items now live in agent_state.db (wire-agent-memory D3).
    agent_memory_module.set_agent_memory_db(
        agent_state_db,
        agent_scope.vector_backend,
    )
    session_index.set_state_db(agent_state_db)
    traces.set_state_db(agent_state_db)
    reflection.set_state_db(agent_state_db)
    memory_proposal_store.set_state_db(agent_state_db)
    # user-memory-v2: facts tables share agent_state.db and the per-agent vector backend.
    facts_store.set_facts_db(agent_state_db, agent_scope.vector_backend)
    approval_request_store.set_state_db(agent_state_db)
    approval_store.set_state_db(agent_state_db)
    allowlist_store.set_state_db(agent_state_db)
    runtime_context.set_state_db(agent_state_db)
    sub_agent_lifecycle.set_state_db(agent_state_db)
    schedule_store.set_state_db(agent_state_db)
    from fleetent.workflow import store as workflow_store

    workflow_store.set_state_db(agent_state_db)
    # unified-file-exchange: wire the artifact ledger + per-scope hard-link views root
    # (data_dir is <agent_home>/data, so the exchange tree lives under data_dir.parent).
    from fleetent import artifact_exchange

    artifact_exchange.set_state_db(agent_state_db)
    artifact_exchange.set_views_root(data_dir.parent / "exchange" / ".views")
    # mcp-per-user-oauth2 (Group 7): wire the standalone encrypted per-user token store +
    # transparent refresher onto the local seams. Pure local wiring (no platform), so it is
    # safe under the no-platform baseline; managed boot (slice 2) injects its own resolver.
    from fleetent.integrations.mcp.standalone_callback import wire_standalone_oauth
    from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore

    wire_standalone_oauth(StandaloneUserTokenStore(agent_state_db))

    # Managed (slice 2): when running under a node (loopback URL injected at spawn), source
    # per-user tokens + register pending-auth through the node loopback instead of the local
    # store. The injected resolver/state-store take precedence over the standalone wiring
    # above; the agent's own TUI token authenticates the loopback. No platform import.
    _loopback_url = os.environ.get("FLEETENT_NODE_LOOPBACK_URL", "").strip()
    _tui_token = os.environ.get("FLEETENT_TUI_TOKEN", "").strip()
    if _loopback_url and _tui_token:
        from fleetent.integrations.mcp import client as _mcp_client
        from fleetent.integrations.mcp.managed_oauth import wire_managed_oauth

        wire_managed_oauth(
            _loopback_url,
            agent_name,
            _tui_token,
            _mcp_client.get_registered_server,
        )

    # agent-hosted-im (Group 3.4): the agent self-hosts its IM connection in all modes, so it
    # resolves inbound IM identities in-process. Under managed placement this wires the loopback-
    # backed identity/address resolvers (no-op under standalone → native-id passthrough).
    _wire_managed_im_resolvers(agent_name, tenant_id)


def _wire_managed_im_resolvers(agent_id: str, tenant_id: str) -> None:
    """Inject the loopback-backed IM identity/address resolvers when node-managed.

    No-op under standalone (no loopback signal) so ``resolve_identity`` keeps native-id
    passthrough and ``resolve_addresses`` stays empty.
    """
    from fleetent import runtime_placement
    from fleetent.im_gateway import access

    if not runtime_placement.is_managed():
        return
    loopback = os.environ.get("FLEETENT_NODE_LOOPBACK_URL", "").strip()
    tui = os.environ.get("FLEETENT_TUI_TOKEN", "").strip()
    if not (loopback and tui):
        return
    access.set_im_identity_resolver(
        access.AgentIdentityResolver(
            loopback_url=loopback, tui_token=tui, agent_name=agent_id, tenant_id=tenant_id
        )
    )
    access.set_im_address_resolver(
        access.AgentAddressResolver(loopback_url=loopback, tui_token=tui, agent_name=agent_id)
    )
    access.set_im_link_confirmer(
        access.AgentLinkConfirmer(loopback_url=loopback, tui_token=tui, agent_name=agent_id)
    )


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
    _init_agent_db_schema(data_dir, agent_name=agent.name, tenant_id=agent.tenant_id)
    from fleetent.runtime.approval_resume import reconcile_expired_approvals

    await reconcile_expired_approvals()
    from fleetent import long_term_ctx
    from fleetent.integrations.sandbox import enablement as sandbox_enablement

    # Select the configured sandbox backend (agent.yaml > platform.yaml > docker) and
    # build the process sandbox manager around it so run_code uses the right backend.
    from fleetent.integrations.sandbox.factory import create_backend
    from fleetent.session import manager as session_mgr
    from fleetent.tools.builtin_tools import init_sandbox_manager

    _configure_knowledge_provider(agent, long_term_ctx=long_term_ctx)
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
            _logger.warn("agent_runtime_sandbox_cleanup_failed", exception=exc)
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
            # mcp-per-user-oauth2 D4: start the idle-reaper for the per-user stdio
            # subprocess pool (no-op unless a per-user oauth stdio server is configured).
            mcp_client.start_stdio_reaper()
        except Exception as exc:  # noqa: BLE001 — MCP unavailable must not abort boot
            _logger.warn("agent_runtime_mcp_register_failed", exception=exc)
    session_mgr.start_session_maintenance()
    # user-memory-v2: start the short-term facts archive sweep. Best-effort — a
    # failure here is logged and never aborts boot (the DB/backend were wired in
    # _init_agent_db_schema via facts_store.set_facts_db).
    try:
        from fleetent.memory import facts_lifecycle, facts_store

        facts_lifecycle.start_archive_sweep(
            facts_store._facts_database(), facts_store._facts_vector_backend
        )
    except Exception as exc:  # noqa: BLE001 — facts sweep must not abort boot
        _logger.warn("agent_runtime_facts_sweep_start_failed", exception=exc)
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
        _logger.warn("session_resume_scan_failed", exception=exc)


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


async def _start_workflow_engine(agent: AgentFile) -> Any:
    """Create + start the per-agent workflow engine, or None when disabled.

    Wires the process-scoped engine + enabled flag the trigger tools read, and starts
    the cold-sweep owner task. Connectors are resolved at delivery time from the live
    registry (like the cron scheduler) so a run started before a connector connects
    still delivers.
    """
    from fleetent import workflow
    from fleetent.workflow.engine import WorkflowEngine

    workflow.set_enabled(agent.workflow.enabled)
    if not agent.workflow.enabled:
        workflow.set_engine(None)
        return None
    from fleetent.im_gateway import connector_registry
    from fleetent.outbound_connectors import resolve_for_runtime

    agent_name = agent.name
    engine = WorkflowEngine(
        agent_name=agent_name,
        max_parallel=agent.workflow.max_parallel,
        connectors_provider=lambda: resolve_for_runtime(
            agent_name, connector_registry.snapshot(agent_name)
        ),
    )
    workflow.set_engine(engine)
    await engine.start()
    return engine


async def boot(
    agent_name: str,
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

    home_dir = resolve_home(agent_name, home)
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
    workflow_engine = await _start_workflow_engine(agent) if with_infra else None

    app = build_app(agent.name) if port is not None else None
    _logger.info("agent_runtime_booted", agent=agent.name, http_port=port, im=start_im)
    return AgentRuntime(
        agent=agent,
        supervisor=supervisor,
        telegram_supervisor=telegram_supervisor,
        workflow_engine=workflow_engine,
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
    agent_name: str,
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
    home_dir = resolve_home(agent_name, home)
    home_dir.mkdir(parents=True, exist_ok=True)
    pid_file = home_dir / ".fleetent.pid"
    pid_file.write_text(str(os.getpid()))

    drain_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGUSR1, drain_event.set)

    try:
        rt = await boot(agent_name, home=home, port=port, start_im=start_im)
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

    @app.get("/oauth/callback")
    async def oauth_callback(code: str | None = None, state: str | None = None) -> Any:
        """Standalone self-hosted OAuth Authorization Code callback (mcp-per-user-oauth2 7.2).

        Identity is reverse-resolved from the one-shot ``state`` alone (never from any login
        state on this request): an invalid / expired / already-used ``state`` is rejected
        with 400 and no token is exchanged or written. On success the ``code`` is exchanged
        and the user's token is stored encrypted in the local per-user library, and a plain
        success page tells the user to return to the conversation.
        """
        from fleetent.integrations.mcp.per_user_tokens import get_local_user_token_store
        from fleetent.integrations.mcp.standalone_callback import handle_oauth_callback

        result = await handle_oauth_callback(
            code=code, state=state, store=get_local_user_token_store()
        )
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.detail)
        return PlainTextResponse("Authorization successful — return to your conversation.")

    @app.get("/mcp/credential")
    async def credential_form(state: str | None = None) -> Any:
        """Standalone self-hosted per-user api-key credential form (mcp-per-user-apikey 3.4).

        Renders a minimal form carrying the one-shot ``state`` (delivered to the user via a
        private DM link). The state is validated only on POST — the GET never consumes it.
        """
        if not state:
            raise HTTPException(status_code=400, detail="missing state")
        from fleetent.integrations.mcp.standalone_credential import render_credential_form

        return HTMLResponse(render_credential_form(state))

    @app.post("/mcp/credential")
    async def credential_submit(state: str = Form(...), key: str = Form(...)) -> Any:
        """Standalone per-user api-key credential submit (mcp-per-user-apikey 3.4).

        Identity is reverse-resolved from the one-shot ``state`` alone (never any login state
        on this request): an invalid / expired / already-used ``state`` is rejected with 400
        and nothing is written. On success the key is stored encrypted under the user's
        ``(user, agent, server)`` triple as ``credential_kind=static``; the key is never
        echoed back.
        """
        from fleetent.integrations.mcp.per_user_tokens import get_local_user_token_store
        from fleetent.integrations.mcp.standalone_credential import handle_credential_submit

        result = handle_credential_submit(state=state, key=key, store=get_local_user_token_store())
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.detail)
        return PlainTextResponse("Credential saved — return to your conversation.")

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
            kwargs["hot_mcp_servers"] = agent.hot_mcp_servers
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

    @app.post("/webhook/{source_id}", status_code=202)
    async def webhook(
        source_id: str,
        request: Request,
        background: BackgroundTasks,
        x_hub_signature_256: str | None = Header(default=None),  # noqa: B008
        x_fleetent_webhook_source: str | None = Header(default=None),  # noqa: B008
    ) -> dict[str, str]:
        """Inbound webhook → run the target agent once as the source's user (live-webhooks).

        Two-state symmetric edge:

        * **standalone** — public, unauthenticated: HMAC over the raw body authenticates the
          caller; the source is resolved from this agent's ``agent.yaml`` ``webhooks.sources``.
        * **managed** — the platform has already verified HMAC against the management-DB
          secret and forwards through the node, supplying the resolved source in the trusted
          ``X-Fleetent-Webhook-Source`` header (same trust model as the ingress principal
          header). HMAC / agent.yaml lookup are then skipped.

        On success the run is scheduled in the background and 202 returns immediately. When the
        source carries a ``reply_target`` the run result is DM'd to that user via directed-reach
        (a no-op in non-managed runtimes); otherwise the reply is a no-op.
        """
        from fleetent import outbound_connectors, webhook_router
        from fleetent.im_gateway import normalizer

        body = await request.body()

        if x_fleetent_webhook_source is not None:
            # Managed: trusted source injected by the platform via the node channel.
            try:
                meta = json.loads(x_fleetent_webhook_source)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="bad webhook source header") from exc
            source = webhook_router.WebhookSource(
                id=source_id,
                user_id=str(meta.get("user_id", "")),
                agent_name=meta.get("agent_name"),
                message_template=meta.get("message_template"),
                reply_target=meta.get("reply_target"),
            )
        else:
            agent = agent_config.current().get(agent_name)
            webhooks = agent.webhooks if agent is not None else None
            sources = webhook_router.sources_from_settings(webhooks.sources if webhooks else [])
            candidate = sources.get(source_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail="unknown webhook source")
            if webhooks is None or not webhooks.enabled:
                raise HTTPException(status_code=403, detail="webhooks disabled")
            if len(body) > webhooks.max_body_bytes:
                raise HTTPException(status_code=413, detail="payload too large")
            if not webhook_router.verify_signature(candidate.secret, body, x_hub_signature_256):
                raise HTTPException(status_code=403, detail="invalid signature")
            source = candidate

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        text = webhook_router.extract_message(source.message_template, payload)

        reply_target = source.reply_target

        async def _reply(reply_text: str, blocks: list[dict[str, Any]] | None = None) -> None:
            # Directed-reach DM to reply_target; notify_user is itself a no-op in non-managed
            # runtimes, so this collapses to no-op there. No reply_target = no delivery.
            if reply_target:
                await outbound_connectors.notify_user(reply_target, reply_text, blocks=blocks)

        msg = normalizer.NormalizedMessage(
            platform="webhook",
            session_id=f"webhook-{source_id}",
            user_id=source.user_id,
            text=text,
            attachments=[],
            reply_func=_reply,
            agent_name=source.agent_name or agent_name,
        )
        background.add_task(normalizer.route, msg)
        return {"status": "accepted", "source_id": source_id}

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
