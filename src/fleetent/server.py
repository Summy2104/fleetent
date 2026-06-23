"""FastAPI control-plane server: admin/console + agent authoring + health/auth.

Agent execution and IM ingress are NOT served here — they run in a standalone agent
runtime (`fleetent agent run`); this app starts agent-free with no IM, loop, or sandbox
(see openspec change ``platform-control-plane``)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, Response

from fleetent import agent_config, agent_store, auth, connectors, cron_scheduler, user_store
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, configure_logging
from fleetent.governance.permission_gate import list_approvals
from fleetent.identity import Principal
from fleetent.im_gateway.access import IMIdentityResolutionError, set_im_identity_resolver
from fleetent.im_gateway.slack_supervisor import SlackSupervisor
from fleetent.integrations.sandbox import (
    Mode,
)
from fleetent.observability.startup_diagnostics import (
    diagnose_database_writable,
    log_config_failed,
    log_config_loaded,
)
from fleetent.platform.agent_management_console import (
    agent_admin_api,
    agent_console_api,
)
from fleetent.platform.agent_statistics import stats_admin_api
from fleetent.platform.askit_console import agent_apply_api
from fleetent.platform.chat_management import chat_admin_api
from fleetent.platform.connector_management import connector_admin_api, vault_provider
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.node_management import (
    node_admin_api,
    node_desired_state_api,
    placement_store,
)
from fleetent.platform.node_management.agent_transport import DirectHttpAgentTransport
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.tenancy import admin_api as tenancy_admin_api
from fleetent.platform.user_management import user_admin_api
from fleetent.platform.user_management.api_key_store import resolve as _resolve_api_key
from fleetent.platform.user_management.platform_bearer_adapter import PlatformBearerAdapter
from fleetent.session import manager as session_mgr
from fleetent.skills import scan as scan_skills
from fleetent.tools.plugin_loader import load_plugins

logger = logging.getLogger(__name__)

ADMIN_UI_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


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


# Per-agent Slack supervisor: one Socket Mode connection per agent declaring
# `im.slack`, sourced from the agent index.
_slack_supervisor = SlackSupervisor()


def _connector_edge_tenant(owner_id: str) -> str:
    agent = agent_config.current().get(owner_id)
    if agent is None:
        return "default"
    return agent.tenant_id


def _resolve_im_identity(owner_id: str, platform: str, platform_user_id: str) -> str:
    from fleetent.platform.im_gateway_management import identity as im_identity

    edge_tenant = _connector_edge_tenant(owner_id)
    user = im_identity.get_or_create(platform, platform_user_id, edge_tenant)
    if user.status == "blocked":
        raise IMIdentityResolutionError("IM identity blocked")
    if user.tenant_id != edge_tenant:
        logger.warning(
            "im_identity_tenant_mismatch owner_id=%s platform=%s platform_user_id=%s "
            "mapped_user_id=%s mapped_tenant=%s edge_tenant=%s",
            owner_id,
            platform,
            platform_user_id,
            user.id,
            user.tenant_id,
            edge_tenant,
        )
        raise IMIdentityResolutionError("IM identity tenant mismatch")
    return user.id


def _cron_principal_recheck(task: dict[str, Any]) -> Principal | None:
    """Platform fire-time creator recheck, injected into cron_scheduler at startup.

    Re-verifies a fired task's creator against the `users` table: blocked → reject;
    a creator that vanished (deleted) with no platform IM origin → reject; otherwise the
    creator's current Principal. A vanished creator that still carries a platform IM
    origin is trusted (channel-guaranteed identity, never resolved through the users
    table). cron_scheduler short-circuits `system`/`default` before delegating here.
    """
    user_id = str(task.get("user_id") or "default")
    u = user_store.get_by_id(user_id)
    if u is not None:
        if u.status == "blocked":
            return None
        return Principal(user_id=u.id, tenant_id=u.tenant_id)
    origin = task.get("origin")
    if isinstance(origin, dict) and origin.get("platform"):
        return Principal(user_id=user_id, tenant_id="default")
    return None


def _build_platform_maintenance_scheduler(
    scheduling: Any = None,
    _scheduler: Any = None,
) -> Any:
    """Build and return a configured (but not yet started) APScheduler for platform-only
    maintenance jobs.  Accepts an optional `_scheduler` for dependency injection in tests."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

    from fleetent.config import SchedulingSettings
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import sweep

    cfg: SchedulingSettings = scheduling if scheduling is not None else SchedulingSettings()
    sched: Any = _scheduler if _scheduler is not None else AsyncIOScheduler()
    sched.add_job(
        sweep,
        trigger="interval",
        seconds=cfg.kb_connector_sweep_interval_seconds,
        id="__kb_connector_sync_sweep__",
        replace_existing=True,
    )
    return sched


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Wire platform api_keys resolver so user_store.authenticate queries the api_keys
    # table (+ legacy fallback) without the module-level platform import removed by #4.
    user_store.set_api_key_resolver(_resolve_api_key)
    connectors.set_provider(vault_provider.get_credential)
    set_im_identity_resolver(_resolve_im_identity)
    # Platform fire-time creator recheck for cron tasks (decouple-cron-principal-recheck):
    # standalone agents never run this lifespan, so they keep trusting the archived IM
    # identity without opening the management DB.
    cron_scheduler.set_principal_resolver(_cron_principal_recheck)

    from fleetent.platform.connector_management import external_credential_store

    agent_store.set_delete_agent_hook(
        lambda aid: external_credential_store.delete_all_credentials_for_user(f"agent:{aid}")
    )

    scan_skills()
    # file-driven-agent-config: scan agent.yaml files once at startup (same lifecycle
    # as scan_skills); the in-memory index drives zero-DB runtime agent resolution.
    agent_config.scan()
    # AR7: load enabled plugins once at startup (same lifecycle as scan_skills /
    # mcp register_all). A missing plugins/ dir or a bad plugin never aborts boot.
    load_plugins()
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

    # The running event loop backs the session governance seams injected below.
    loop = asyncio.get_running_loop()

    def _pg_transcript(session_id: str) -> list[dict[str, Any]]:
        return asyncio.run_coroutine_threadsafe(session_mgr.load(session_id), loop).result()

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

    # Platform-side maintenance scheduler: runs sweep jobs in the platform process so
    # agent-runtime cron_scheduler stays free of platform imports (boundary contract).
    from fleetent.config import SchedulingSettings

    platform_maint_sched = _build_platform_maintenance_scheduler(SchedulingSettings())
    platform_maint_sched.start()

    yield

    if platform_maint_sched.running:
        platform_maint_sched.shutdown(wait=False)
    # Release MCP session hosts (platform registers global servers via register_all). Each
    # host tears down on its own task; failures are contained inside aclose_all().
    try:
        from fleetent.integrations import mcp

        await mcp.aclose_all()
    except Exception as exc:  # noqa: BLE001 — containment: shutdown must not raise
        logger.warning("mcp_aclose_all_failed error=%s", exc)
    finally:
        set_im_identity_resolver(None)


app = FastAPI(title="fleetent", lifespan=lifespan)
app.include_router(user_admin_api.router)
app.include_router(skill_admin_api.router)
app.include_router(provider_admin_api.router)
app.include_router(kb_admin_api.router)
app.include_router(connector_admin_api.router)
app.include_router(chat_admin_api.router)
app.include_router(agent_console_api.router)
app.include_router(agent_admin_api.router)
app.include_router(stats_admin_api.router)
app.include_router(agent_apply_api.router)
app.include_router(node_desired_state_api.router)
app.include_router(node_admin_api.router)
app.include_router(tenancy_admin_api.router)


def _remove_legacy_admin_ui_route() -> None:
    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", None) != "/admin/ui"
    ]


_remove_legacy_admin_ui_route()


def _spa_index_path() -> Path:
    return _admin_ui_dist_dir() / "index.html"


def _admin_ui_dist_dir() -> Path:
    override = os.environ.get("FLEETENT_ADMIN_UI_DIST")
    if override:
        return Path(override)
    return ADMIN_UI_DIST_DIR


def _serve_spa_file(asset_path: str) -> Response:
    root = _admin_ui_dist_dir().resolve()
    requested = (root / asset_path).resolve()
    if requested.is_file() and str(requested).startswith(str(root)):
        return FileResponse(requested)

    index_path = _spa_index_path()
    if not index_path.is_file():
        raise HTTPException(status_code=503, detail="admin frontend dist not built")

    if asset_path and "." in Path(asset_path).name:
        raise HTTPException(status_code=404, detail="asset not found")

    return HTMLResponse(
        index_path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"}
    )


@app.get("/admin/ui", response_class=HTMLResponse)
def admin_ui() -> Response:
    return _serve_spa_file("")


@app.get("/admin/ui/{asset_path:path}", response_class=HTMLResponse)
def admin_ui_spa(asset_path: str) -> Response:
    return _serve_spa_file(asset_path)


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

    def _console_delete(name: str) -> bool:
        return agent_store.delete_agent(name)

    def _apply_create(
        name: str,
        system_prompt: str,
        allowed_tools: list[str],
        model_overrides: dict[str, Any] | None = None,
    ) -> int:
        agent_id = agent_store.create_agent(
            name,
            system_prompt,
            allowed_tools,
            model_overrides=model_overrides,
        ).id
        return agent_id

    def _apply_update(
        name: str,
        system_prompt: str,
        allowed_tools: list[str],
        model_overrides: dict[str, Any] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "allowed_tools": allowed_tools,
        }
        if model_overrides is not None:
            kwargs["model_overrides"] = model_overrides
        agent_store.create_version(name, **kwargs)

    agent_console_api.get_agent_def = _get_def
    agent_console_api.create_agent_def = _console_create
    agent_console_api.update_agent_def = _console_update
    agent_console_api.delete_agent_def = _console_delete
    agent_console_api.set_agent_icon = agent_store.set_icon
    agent_console_api.agent_icons = agent_store.icons_by_name

    agent_apply_api.get_agent_def = _get_def
    agent_apply_api.create_agent_def = _apply_create
    agent_apply_api.update_agent_def = _apply_update


wire_agent_store_seams()


_platform_bearer = PlatformBearerAdapter()
_agent_transport = DirectHttpAgentTransport()


async def _authenticate(authorization: str = Header()) -> Principal:
    """Resolve a Bearer API key to a Principal. Raises 401 if invalid/blocked."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    principal = _platform_bearer(api_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return principal


def _require_admin_session(authorization: str = Header(default="")) -> user_store.User:
    if not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="Session token required")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, 1800)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, {"admin", "built_in_admin"}):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _resolve_agent_node_id(agent_name: str) -> str:
    agent = agent_store.get_by_name(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent {agent_name!r} not found")
    placement = placement_store.get_for_agent(agent.id)
    if placement is None:
        raise HTTPException(status_code=503, detail=f"agent {agent_name!r} has no node placement")
    return str(placement["node_id"])


def _slack_adapter_configured() -> bool:
    """Whether any indexed agent declares a per-agent Slack IM binding."""
    return any(agent.im.slack is not None for agent in agent_config.current().agents.values())


def _telegram_adapter_configured() -> bool:
    """Whether any indexed agent declares a per-agent Telegram IM binding."""
    return any(agent.im.telegram is not None for agent in agent_config.current().agents.values())


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


@app.post("/admin/agents/{agent_name}/chat")
async def managed_agent_chat(
    agent_name: str,
    request: Request,
    admin: user_store.User = Depends(_require_admin_session),  # noqa: B008
) -> Response:
    return await _agent_transport.chat(
        _resolve_agent_node_id(agent_name),
        agent_name,
        await request.body(),
        content_type=request.headers.get("content-type", "application/json"),
        principal=Principal(user_id=admin.id, tenant_id=admin.tenant_id),
    )


@app.websocket("/admin/agents/{agent_name}/ws")
async def managed_agent_ws(websocket: WebSocket, agent_name: str) -> None:
    admin = _require_admin_session(websocket.headers.get("authorization", ""))
    await _agent_transport.ws(
        _resolve_agent_node_id(agent_name),
        agent_name,
        websocket,
        principal=Principal(user_id=admin.id, tenant_id=admin.tenant_id),
    )
