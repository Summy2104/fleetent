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

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from fleetent import agent_config, agent_store, user_store
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, configure_logging
from fleetent.cron_scheduler import CronScheduler
from fleetent.governance.permission_gate import (
    _default_gate,
    cleanup_stale_approvals,
    list_approvals,
)
from fleetent.im_gateway import telegram as telegram_adapter
from fleetent.im_gateway.slack_supervisor import SlackSupervisor
from fleetent.integrations.sandbox import (
    Mode,
)
from fleetent.model import ROUTES
from fleetent.observability.startup_diagnostics import (
    diagnose_database_writable,
    diagnose_provider_keys,
    log_config_failed,
    log_config_loaded,
)
from fleetent.platform.agent_management_console import agent_admin_api, agent_console_api
from fleetent.platform.agent_statistics import stats_admin_api
from fleetent.platform.askit_console import agent_apply_api
from fleetent.platform.chat_management import chat_admin_api
from fleetent.platform.connector_management import connector_admin_api
from fleetent.platform.im_gateway_management import admin_api, connector_manager
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.resource_monitoring import collectors, monitor_admin_api
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.user_management import user_admin_api
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


# Owner-level connector manager. Slack is intentionally absent: it is per-agent,
# supervised by `_slack_supervisor` from the agent index (per-agent-slack-connector).
_connector_manager = connector_manager.ConnectorManager(
    factories={
        "telegram": telegram_adapter.run,
    }
)

# Per-agent Slack supervisor: one Socket Mode connection per agent declaring
# `connectors.slack`, sourced from the agent index.
_slack_supervisor = SlackSupervisor()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scan_skills()
    # file-driven-agent-config: scan agent.yaml files once at startup (same lifecycle
    # as scan_skills); the in-memory index drives zero-DB runtime agent resolution.
    agent_config.scan()
    # AR7: load enabled plugins once at startup (same lifecycle as scan_skills /
    # mcp register_all). A missing plugins/ dir or a bad plugin never aborts boot.
    load_plugins()
    cleanup_stale_approvals()
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:
        log_config_failed(exc)
        raise
    configure_logging(settings)
    log_config_loaded()
    diagnose_database_writable(settings.database_url)
    diagnose_provider_keys(ROUTES.values())

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
        af = agent_config.current().get(agent_name) if agent_name else None
        kwargs: dict[str, Any] = {"user_id": "playground", "session_id": session_id}
        if af is not None:
            kwargs["system_prompt"] = af.system_prompt
            kwargs["allowed_tools"] = af.allowed_tools + expand_plugin_patterns(af.plugins)
            kwargs["agent_name"] = af.name
            kwargs["agent_features"] = af.features
            kwargs["allowed_skills"] = af.allowed_skills
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

    # Best-effort scheduler start: a missing/locked scheduled_tasks table (e.g. an
    # unmigrated DB) must not prevent the HTTP API from serving, consistent with the
    # sandbox-cleanup / IM-adapter best-effort pattern above. Surfaced via warning.
    cron = CronScheduler(settings=settings.scheduling)
    try:
        await cron.start()
        cron.add_interval_job(
            _run_monitoring_cycle, collectors.COLLECT_INTERVAL_SECONDS, "monitoring_collect"
        )
        cron.add_interval_job(
            _run_playground_retention,
            _PLAYGROUND_RETENTION_INTERVAL_SECONDS,
            "playground_retention",
        )
    except Exception as exc:
        logger.warning("cron_scheduler_start_failed error=%s", exc)

    yield

    try:
        await cron.shutdown()
    except Exception as exc:
        logger.warning("cron_scheduler_shutdown_failed error=%s", exc)


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
app.include_router(monitor_admin_api.router)
app.include_router(agent_apply_api.router)


def _agent_def_dict(agent: agent_store.Agent | None) -> dict[str, Any] | None:
    """Serialize an Agent to the dict shape the console/apply seams promise."""
    if agent is None:
        return None
    return {
        "id": agent.id,
        "system_prompt": agent.system_prompt,
        "allowed_tools": agent.allowed_tools,
        "plugins": agent.plugins,
        "features": agent.features,
        "skills_dir": agent.skills_dir,
        "mcp_server_ids": agent.mcp_server_ids,
        "model_overrides": agent.model_overrides,
        "memory_namespace": agent.memory_namespace,
        "template_id": agent.template_id,
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
        template_id: str | None = None,
        plugins: list[str] | None = None,
        features: dict[str, Any] | None = None,
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
            template_id=template_id,
        )

    def _console_update(
        name: str,
        system_prompt: str | None,
        allowed_tools: list[str] | None,
        skills_dir: str | None = None,
        mcp_server_ids: list[str] | None = None,
        model_overrides: dict[str, Any] | None = None,
        memory_namespace: str | None = None,
    ) -> None:
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

    def _console_delete(name: str) -> bool:
        return agent_store.delete_agent(name)

    def _apply_create(name: str, system_prompt: str, allowed_tools: list[str]) -> int:
        return agent_store.create_agent(name, system_prompt, allowed_tools).id

    def _apply_update(name: str, system_prompt: str, allowed_tools: list[str]) -> None:
        agent_store.create_version(name, system_prompt=system_prompt, allowed_tools=allowed_tools)

    agent_console_api.get_agent_def = _get_def
    agent_console_api.create_agent_def = _console_create
    agent_console_api.update_agent_def = _console_update
    agent_console_api.delete_agent_def = _console_delete

    agent_apply_api.get_agent_def = _get_def
    agent_apply_api.create_agent_def = _apply_create
    agent_apply_api.update_agent_def = _apply_update


wire_agent_store_seams()


class ChatRequest(BaseModel):
    message: str


def _emit_over_quota_event(user_id: str) -> None:
    """Emit an over-quota event so operators can see who hit their limit."""
    logger.warning("over_quota user_id=%s", user_id)


def _run_monitoring_cycle() -> None:
    """One periodic monitoring tick: collect samples, prune, escalate stale criticals.

    Failures never crash the scheduler — each step is logged and isolated so a flaky
    collection source cannot stop alert escalation.
    """
    for step in (
        collectors.collect_once,
        collectors.purge_expired,
        monitor_admin_api.escalate_pending,
    ):
        try:
            step()
        except Exception:  # noqa: BLE001 — keep the periodic job alive
            logger.exception("monitoring_cycle_step_failed step=%s", step.__name__)


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


async def _authenticate(authorization: str = Header()) -> tuple[user_store.User, dict[str, Any]]:
    """Resolve a Bearer API key to (User, key_metadata). Raises 401 if invalid/blocked."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    result = user_store.authenticate(api_key)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return result


@app.get("/health")
async def health(request: Request) -> dict:  # type: ignore[type-arg]
    settings = Settings()
    # SB3: surface the effective sandbox mode resolved at startup; default to off
    # when the state is somehow unset (e.g. lifespan not run) so we never crash.
    mode: Mode = getattr(request.app.state, "sandbox_mode", Mode.OFF)
    docker_available: bool = getattr(request.app.state, "sandbox_docker_available", False)
    sandbox: dict[str, Any] = {"mode": mode.value, "docker_available": docker_available}
    if not docker_available:
        sandbox["note"] = "off (docker unavailable)"
    return {
        "status": "ok",
        "adapters": {
            "slack": bool(settings.slack_bot_token),
            "telegram": bool(settings.telegram_bot_token),
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
