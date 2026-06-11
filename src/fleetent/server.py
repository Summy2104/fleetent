"""FastAPI control-plane server: admin/console + agent authoring + health/auth.

Agent execution and IM ingress are NOT served here — they run in a standalone agent
runtime (`fleetent agent run`); this app starts agent-free with no IM, loop, or sandbox
(see openspec change ``platform-control-plane``)."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from fleetent import agent_config, agent_store, user_store
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, configure_logging
from fleetent.governance.permission_gate import (
    _default_gate,
    list_approvals,
)
from fleetent.identity import Principal
from fleetent.im_gateway.slack_supervisor import SlackSupervisor
from fleetent.integrations.sandbox import (
    Mode,
)
from fleetent.observability.startup_diagnostics import (
    diagnose_database_writable,
    log_config_failed,
    log_config_loaded,
)
from fleetent.platform.agent_lifecycle import lifecycle_admin_api, materialize
from fleetent.platform.agent_management_console import (
    agent_admin_api,
    agent_admin_store,
    agent_console_api,
)
from fleetent.platform.agent_statistics import stats_admin_api
from fleetent.platform.askit_console import agent_apply_api
from fleetent.platform.chat_management import chat_admin_api
from fleetent.platform.connector_management import connector_admin_api
from fleetent.platform.im_gateway_management import admin_api, connector_manager
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.user_management import user_admin_api
from fleetent.platform.user_management.api_key_store import resolve as _resolve_api_key
from fleetent.platform.user_management.platform_bearer_adapter import PlatformBearerAdapter
from fleetent.runtime import run_stream
from fleetent.session import manager as session_mgr
from fleetent.skills import scan as scan_skills
from fleetent.tools.plugin_loader import expand_plugin_patterns, load_plugins

logger = logging.getLogger(__name__)


def _admin_login_url(router_prefix: str) -> str:
    """Build the full admin login URL from the uvicorn CLI args.

    The bind address is owned by uvicorn, not the app, so derive it from argv.
    Falls back to uvicorn's own defaults (127.0.0.1:8000).
    """
    host, port = "127.0.0.1", 8000
    args = sys.argv
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg.startswith("--host="):
            host = arg.split("=", 1)[1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
    # 0.0.0.0 binds all interfaces but is not directly reachable; show loopback.
    display_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    return f"http://{display_host}:{port}{router_prefix}/ui"


# Owner-level connector manager. Slack and Telegram are intentionally absent: both are
# per-agent, supervised from the agent index (per-agent-slack-connector /
# per-agent-telegram-connector). No owner-level adapter factories remain.
_connector_manager = connector_manager.ConnectorManager(factories={})

# Per-agent Slack supervisor: one Socket Mode connection per agent declaring
# `connectors.slack`, sourced from the agent index.
_slack_supervisor = SlackSupervisor()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Wire platform api_keys resolver so user_store.authenticate queries the api_keys
    # table (+ legacy fallback) without the module-level platform import removed by #4.
    user_store.set_api_key_resolver(_resolve_api_key)

    scan_skills()
    # file-driven-agent-config: scan agent.yaml files once at startup (same lifecycle
    # as scan_skills); the in-memory index drives zero-DB runtime agent resolution.
    agent_config.scan()
    # AR7: load enabled plugins once at startup (same lifecycle as scan_skills /
    # mcp register_all). A missing plugins/ dir or a bad plugin never aborts boot.
    load_plugins()
    # approval-suspend-resume: reconcile only EXPIRED pending approvals; non-expired
    # ones survive the restart and stay resolvable (no blanket timeout anymore).
    from fleetent.runtime.approval_resume import reconcile_expired_approvals

    await reconcile_expired_approvals()
    try:
        settings = Settings()
    except Exception as exc:
        log_config_failed(exc)
        raise
    configure_logging(settings)
    log_config_loaded()
    diagnose_database_writable(settings.database_url)

    # platform-control-plane: agent execution (loop + sandbox + IM) runs only in an
    # `fleetent agent run` process; the platform no longer probes Docker, registers
    # agent-use MCP, maintains sessions, or starts IM connectors at boot.

    # Seed the built-in admin on first boot; log the one-time initial password.
    admin_seed = seed_builtin_admin()
    if admin_seed is not None:
        admin_user, temp_password = admin_seed
        logger.warning(
            "builtin_admin_seeded username=%s initial_password=%s (must change on first login)",
            admin_user.name,
            temp_password,
        )

    logger.info("admin_login_url url=%s", _admin_login_url(user_admin_api.router.prefix))

    # The running event loop, used by the admin "Chat" playground seams below to drive
    # on-demand turns from sync admin handlers.
    loop = asyncio.get_running_loop()

    # Wire the admin "Chat" playground to the real agent loop (mirrors /chat): the
    # selected agent is resolved by name from its file-driven config, and the turn
    # runs through run_stream against the playground session. Without this the
    # playground seams are inert placeholders.
    def _pg_run(
        agent_name: str,
        session_id: str,
        message: str,
        overrides: dict[str, Any] | None,
        bypass_medium: bool,
    ) -> dict[str, Any]:
        from fleetent.runtime.snapshot import _governance_from_file

        af = agent_config.current().get(agent_name) if agent_name else None
        kwargs: dict[str, Any] = {
            "principal": Principal(user_id="playground", tenant_id="default"),
            "session_id": session_id,
        }
        if af is not None:
            kwargs["system_prompt"] = af.system_prompt
            kwargs["allowed_tools"] = af.allowed_tools + expand_plugin_patterns(af.plugins)
            kwargs["agent_name"] = af.name
            kwargs["agent_features"] = af.features
            kwargs["allowed_skills"] = af.allowed_skills
            kwargs["governance"] = _governance_from_file(af)
        events: list[dict[str, Any]] = []

        async def _collect() -> str:
            reply = ""
            try:
                async for ev in run_stream(message, **kwargs):
                    etype = ev.get("type")
                    if etype == "done":
                        reply = ev.get("content", "")
                    elif etype in ("tool_call", "tool_result", "error"):
                        events.append(ev)
            except Exception as exc:  # noqa: BLE001 — surface as a turn error, never a 500
                events.append({"type": "error", "content": str(exc)})
            return reply

        reply = asyncio.run_coroutine_threadsafe(_collect(), loop).result()
        return {"reply": reply, "events": events}

    def _pg_transcript(session_id: str) -> list[dict[str, Any]]:
        return asyncio.run_coroutine_threadsafe(session_mgr.load(session_id), loop).result()

    chat_admin_api.run_playground = _pg_run
    chat_admin_api.load_transcript = _pg_transcript
    chat_admin_api.clear_session = lambda session_id: asyncio.run_coroutine_threadsafe(
        session_mgr.clear(session_id), loop
    ).result()
    chat_admin_api.inject = lambda session_id, role, content: asyncio.run_coroutine_threadsafe(
        session_mgr.inject_message(session_id, role, content), loop
    ).result()
    chat_admin_api.reset_session = lambda session_id, keep_turns: asyncio.run_coroutine_threadsafe(
        session_mgr.reset(session_id, keep_turns), loop
    ).result()

    # Platform-maintenance scheduler only (agent-owned-scheduled-tasks): user scheduled
    # tasks are agent-runtime-owned and fired by each agent process, NOT the platform
    # server. The platform keeps a bare scheduler purely for its own housekeeping
    # (expired-playground purge); best-effort so a failure never blocks serving.
    maint = AsyncIOScheduler()
    try:
        maint.add_job(
            _run_playground_retention,
            trigger="interval",
            seconds=_PLAYGROUND_RETENTION_INTERVAL_SECONDS,
            id="playground_retention",
            replace_existing=True,
        )
        maint.start()
    except Exception as exc:
        logger.warning("platform_maintenance_scheduler_start_failed error=%s", exc)

    yield

    try:
        if maint.running:
            maint.shutdown(wait=False)
    except Exception as exc:
        logger.warning("platform_maintenance_scheduler_shutdown_failed error=%s", exc)


app = FastAPI(title="fleetent", lifespan=lifespan)
app.include_router(user_admin_api.router)
app.include_router(skill_admin_api.router)
app.include_router(provider_admin_api.router)
app.include_router(kb_admin_api.router)
app.include_router(connector_admin_api.router)
app.include_router(admin_api.router)
app.include_router(chat_admin_api.router)
app.include_router(agent_console_api.router)
app.include_router(agent_admin_api.router)
app.include_router(stats_admin_api.router)
app.include_router(agent_apply_api.router)
app.include_router(lifecycle_admin_api.router)


_UNSET: Any = object()  # distinguishes "field omitted" from an explicit None (clear)


def _agent_def_dict(agent: agent_store.Agent | None) -> dict[str, Any] | None:
    """Serialize an Agent to the dict shape the console/apply seams promise."""
    if agent is None:
        return None
    version = 1
    if agent.active_version_id is not None:
        av = agent_store.get_version_by_id(agent.active_version_id)
        if av is not None:
            version = av.version
    return {
        "id": agent.id,
        "version": version,  # active snapshot number (read-only in the console)
        "tenant_id": agent.tenant_id,
        "team_id": agent.team_id,
        "system_prompt": agent.system_prompt,
        "allowed_tools": agent.allowed_tools,
        "plugins": agent.plugins,
        "features": agent.features,
        "skills_dir": agent.skills_dir,
        "mcp_server_ids": agent.mcp_server_ids,
        "model_overrides": agent.model_overrides,
        "memory_namespace": agent.memory_namespace,
        "icon": agent.icon,
        "config_overrides": agent.config_overrides,
    }


def wire_agent_store_seams() -> None:
    """Bridge the console + apply agent seams to agent_store (production wiring).

    Without this, clone/create/update/delete and apply act as inert stubs.
    """

    def _get_def(name: str) -> dict[str, Any] | None:
        return _agent_def_dict(agent_store.get_by_name(name))

    def _console_create(
        name: str,
        system_prompt: str,
        allowed_tools: list[str],
        skills_dir: str | None = None,
        mcp_server_ids: list[str] | None = None,
        model_overrides: dict[str, Any] | None = None,
        memory_namespace: str = "default",
        plugins: list[str] | None = None,
        features: dict[str, Any] | None = None,
        icon: str | None = None,
        tenant_id: str = "default",
        team_id: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        agent_store.create_agent(
            name,
            system_prompt,
            allowed_tools,
            plugins=plugins,
            features=features,
            skills_dir=skills_dir,
            mcp_server_ids=mcp_server_ids,
            model_overrides=model_overrides,
            memory_namespace=memory_namespace,
            icon=icon,
            tenant_id=tenant_id,
            team_id=team_id,
            config_overrides=config_overrides,
        )
        # platform-agent-lifecycle: materialize the runnable home on create.
        materialize.materialize_from_store(name)

    def _console_update(
        name: str,
        system_prompt: str | None,
        allowed_tools: list[str] | None,
        skills_dir: str | None = None,
        mcp_server_ids: list[str] | None = None,
        model_overrides: dict[str, Any] | None = None,
        memory_namespace: str | None = None,
        tenant_id: str | object = _UNSET,
        team_id: str | None | object = _UNSET,
        config_overrides: dict[str, Any] | object = _UNSET,
    ) -> None:
        # tenant/team/config_overrides are agent-level (not versioned). Only set fields the
        # caller passed; an explicit None clears tenant/team (vs _UNSET = leave unchanged).
        if tenant_id is not _UNSET or team_id is not _UNSET:
            current = agent_store.get_by_name(name)
            if current is not None:
                agent_store.set_identity(
                    name,
                    current.tenant_id if tenant_id is _UNSET else str(tenant_id),
                    current.team_id if team_id is _UNSET else team_id,  # type: ignore[arg-type]
                )
        if config_overrides is not _UNSET:
            agent_store.set_config_overrides(name, config_overrides)  # type: ignore[arg-type]
        kwargs: dict[str, Any] = {}
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        if allowed_tools is not None:
            kwargs["allowed_tools"] = allowed_tools
        if skills_dir is not None:
            kwargs["skills_dir"] = skills_dir
        if mcp_server_ids is not None:
            kwargs["mcp_server_ids"] = mcp_server_ids
        if model_overrides is not None:
            kwargs["model_overrides"] = model_overrides
        if memory_namespace is not None:
            kwargs["memory_namespace"] = memory_namespace
        agent_store.create_version(name, **kwargs)
        # platform-agent-lifecycle: re-materialize the home on update.
        materialize.materialize_from_store(name)

    def _console_delete(name: str) -> bool:
        return agent_store.delete_agent(name)

    def _console_rename(old_name: str, new_name: str) -> None:
        agent_store.rename_agent(old_name, new_name)
        agent_admin_store.rename(old_name, new_name)

    def _apply_create(name: str, system_prompt: str, allowed_tools: list[str]) -> int:
        agent_id = agent_store.create_agent(name, system_prompt, allowed_tools).id
        materialize.materialize_from_store(name)
        return agent_id

    def _apply_update(name: str, system_prompt: str, allowed_tools: list[str]) -> None:
        agent_store.create_version(name, system_prompt=system_prompt, allowed_tools=allowed_tools)
        materialize.materialize_from_store(name)

    agent_console_api.get_agent_def = _get_def
    agent_console_api.create_agent_def = _console_create
    agent_console_api.update_agent_def = _console_update
    agent_console_api.delete_agent_def = _console_delete
    agent_console_api.rename_agent_def = _console_rename
    agent_console_api.set_agent_icon = agent_store.set_icon
    agent_console_api.agent_icons = agent_store.icons_by_name

    agent_apply_api.get_agent_def = _get_def
    agent_apply_api.create_agent_def = _apply_create
    agent_apply_api.update_agent_def = _apply_update


wire_agent_store_seams()


_PLAYGROUND_RETENTION_INTERVAL_SECONDS = 24 * 3600


def _run_playground_retention() -> None:
    """Daily sweep: drop unpinned, expired playground sessions. Failures are isolated."""
    import os

    if not os.environ.get("DATABASE_URL"):
        return
    try:
        chat_admin_api.purge_expired_playground()
    except Exception:  # noqa: BLE001 — keep the periodic job alive
        logger.exception("playground_retention_failed")


def agent_routing_status(agent_name: str) -> str:
    """Lifecycle status of a console-managed agent ('enabled'/'disabled'/'archived').

    Advisory: if no managed DB is configured or the lookup fails, default to 'enabled'
    so the hot path is never blocked by an observability concern.
    """
    import os

    if not os.environ.get("DATABASE_URL"):
        return "enabled"
    try:
        from fleetent.platform.agent_management_console import agent_admin_store

        return str(agent_admin_store.get_state(agent_name)["status"])
    except Exception:  # noqa: BLE001 — advisory check, never block chat on failure
        logger.exception("agent_status_lookup_failed agent=%s", agent_name)
        return "enabled"


_platform_bearer = PlatformBearerAdapter()


async def _authenticate(authorization: str = Header()) -> Principal:
    """Resolve a Bearer API key to a Principal. Raises 401 if invalid/blocked."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    principal = _platform_bearer(api_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return principal


def _slack_adapter_configured() -> bool:
    """Whether any indexed agent declares a per-agent Slack connector."""
    return any(
        agent.connectors.slack is not None for agent in agent_config.current().agents.values()
    )


def _telegram_adapter_configured() -> bool:
    """Whether any indexed agent declares a per-agent Telegram connector."""
    return any(
        agent.connectors.telegram is not None for agent in agent_config.current().agents.values()
    )


@app.get("/health")
async def health(request: Request) -> dict:  # type: ignore[type-arg]
    # SB3: surface the effective sandbox mode + selected backend resolved at startup;
    # default to off/docker/unavailable when state is unset (e.g. lifespan not run) so
    # we never crash. `backend`/`backend_available` are backend-neutral (Docker or
    # microsandbox); the legacy `docker_available` field is replaced.
    mode: Mode = getattr(request.app.state, "sandbox_mode", Mode.OFF)
    backend: str = getattr(request.app.state, "sandbox_backend", "docker")
    backend_available: bool = getattr(request.app.state, "sandbox_backend_available", False)
    sandbox: dict[str, Any] = {
        "mode": mode.value,
        "backend": backend,
        "backend_available": backend_available,
    }
    if not backend_available:
        sandbox["note"] = f"off ({backend} unavailable)"
    return {
        "status": "ok",
        "adapters": {
            "slack": _slack_adapter_configured(),
            "telegram": _telegram_adapter_configured(),
        },
        "sandbox": sandbox,
    }


@app.get("/approvals")
async def get_approvals(status: str | None = None) -> list:  # type: ignore[type-arg]
    return list_approvals(status=status)


class ApprovalRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    approver_user_id: str = "anonymous"


@app.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, req: ApprovalRequest) -> dict:  # type: ignore[type-arg]
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
    found = await _default_gate.resolve(
        approval_id=approval_id,
        decision=req.decision,  # type: ignore[arg-type]
        approver_user_id=req.approver_user_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found or expired")
    return {"status": "ok", "approval_id": approval_id, "decision": req.decision}
