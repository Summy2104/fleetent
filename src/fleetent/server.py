"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from fleetent import user_store
from fleetent.agent_loop import run_stream
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, WebhooksSettings, configure_logging, load_mcp_server_settings
from fleetent.cron_scheduler import CronScheduler
from fleetent.governance import quota
from fleetent.governance.permission_gate import (
    _default_gate,
    cleanup_stale_approvals,
    list_approvals,
)
from fleetent.im_gateway import slack as slack_adapter
from fleetent.im_gateway import telegram as telegram_adapter
from fleetent.integrations import mcp as mcp_client
from fleetent.integrations.mcp import McpServerConfig
from fleetent.model_router import ROUTES
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
from fleetent.platform.im_gateway_management import im_admin_api, im_connector_manager
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.resource_monitoring import collectors, monitor_admin_api
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.user_management import api_key_store, user_admin_api
from fleetent.skill_registry import scan as scan_skills

logger = logging.getLogger(__name__)

LEGACY_MCP_CONFIG_PATH: Path = Path("config/mcp.yaml")
LEGACY_WEBHOOK_CONFIG_PATH: Path = Path("config/webhooks.yaml")
_webhook_sources: dict[str, Any] = {}


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


_connector_manager = im_connector_manager.ConnectorManager(
    factories={
        "slack": slack_adapter.run,
        "telegram": telegram_adapter.run,
    }
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scan_skills()
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

    if LEGACY_MCP_CONFIG_PATH.exists():
        raise RuntimeError(
            "Legacy config/mcp.yaml is no longer supported; move MCP servers to "
            "config/mcp.servers.yaml."
        )

    if settings.mcp.enabled:
        server_settings = load_mcp_server_settings()
        if server_settings:
            servers = [McpServerConfig(**server.model_dump()) for server in server_settings]
            await mcp_client.register_all(servers)

    if LEGACY_WEBHOOK_CONFIG_PATH.exists():
        raise RuntimeError(
            "Legacy config/webhooks.yaml is no longer supported; webhook source management "
            "will move to a runtime API / store."
        )

    app.state.webhook_settings = settings.webhooks
    _webhook_sources.clear()

    # IM connectors are driven by the registry via the manager: only enabled platforms
    # with usable config start. Wire the admin-API seams to this running manager so
    # enable/disable endpoints can drive lifecycle without importing the loop.
    loop = asyncio.get_running_loop()
    im_admin_api.start_connector = lambda platform: asyncio.run_coroutine_threadsafe(
        _connector_manager.start(platform), loop
    ).result()
    im_admin_api.stop_connector = lambda platform: asyncio.run_coroutine_threadsafe(
        _connector_manager.stop(platform), loop
    ).result()
    await _connector_manager.start_all_enabled()

    cron = CronScheduler(settings=settings.scheduling)
    await cron.start()
    cron.add_interval_job(
        _run_monitoring_cycle, collectors.COLLECT_INTERVAL_SECONDS, "monitoring_collect"
    )
    cron.add_interval_job(
        _run_playground_retention, _PLAYGROUND_RETENTION_INTERVAL_SECONDS, "playground_retention"
    )

    yield

    for platform in list(_connector_manager.running()):
        await _connector_manager.stop(platform)
    await cron.shutdown()
    await mcp_client.close()


app = FastAPI(title="fleetent", lifespan=lifespan)
app.include_router(user_admin_api.router)
app.include_router(skill_admin_api.router)
app.include_router(provider_admin_api.router)
app.include_router(kb_admin_api.router)
app.include_router(connector_admin_api.router)
app.include_router(im_admin_api.router)
app.include_router(chat_admin_api.router)
app.include_router(agent_console_api.router)
app.include_router(agent_admin_api.router)
app.include_router(stats_admin_api.router)
app.include_router(monitor_admin_api.router)
app.include_router(agent_apply_api.router)


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
async def health() -> dict[str, Any]:
    settings = Settings()  # type: ignore[call-arg]
    return {
        "status": "ok",
        "adapters": {
            "slack": bool(settings.slack_bot_token),
            "telegram": bool(settings.telegram_bot_token),
        },
    }


@app.get("/approvals")
async def get_approvals(status: str | None = None) -> list[dict[str, Any]]:
    return list_approvals(status=status)


class ApprovalRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    approver_user_id: str = "anonymous"


@app.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, req: ApprovalRequest) -> dict[str, str]:
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


@app.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    auth_result: tuple[user_store.User, dict[str, Any]] = Depends(_authenticate),
    x_platform: str | None = Header(default=None),
    x_channel_id: str | None = Header(default=None),
) -> StreamingResponse:
    from fleetent import agent_runtime

    user, key_meta = auth_result
    user_id = user.id

    snapshot = agent_runtime.resolve_agent_for_request(
        platform=x_platform or "",
        channel_id=x_channel_id or "",
        user_id=user_id,
    )
    system_prompt = snapshot.system_prompt if snapshot is not None else None
    agent_name = snapshot.name if snapshot is not None else None

    # Lifecycle gate: disabled / archived agents are not routable (no agent loop entry).
    if agent_name is not None:
        status = agent_routing_status(agent_name)
        if status == "disabled":
            raise HTTPException(status_code=403, detail="该 Agent 已停用")
        if status == "archived":
            raise HTTPException(status_code=403, detail="该 Agent 已归档，无法路由")

    # API-key scope: the key may be restricted to specific agents.
    if agent_name is not None and not api_key_store.check_scope(key_meta["scope"], agent_name):
        raise HTTPException(status_code=403, detail="scope does not allow this agent")

    # Usage quota: reject when the user's or global limit is already exhausted.
    if not quota.check_quota(user_id):
        _emit_over_quota_event(user_id)
        raise HTTPException(status_code=429, detail="usage quota exceeded")

    # Record key usage (source IP / UA / call count). Legacy keys have no row id.
    if key_meta.get("id") is not None:
        api_key_store.record_usage(
            key_meta["id"],
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )
    quota.record_usage(user_id, tokens=0)  # token-precise accounting: see follow-up note

    async def _stream() -> AsyncGenerator[str, None]:
        try:
            kwargs: dict[str, Any] = {"user_id": user_id}
            if system_prompt is not None:
                kwargs["system_prompt"] = system_prompt
            if agent_name is not None:
                kwargs["agent_name"] = agent_name
            if snapshot is not None:
                kwargs["snapshot"] = snapshot
            async for event in run_stream(req.message, **kwargs):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/webhook/{source_id}")
async def webhook(source_id: str, request: Request) -> Response:
    from fleetent import webhook_router as wr
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    webhook_settings = getattr(request.app.state, "webhook_settings", WebhooksSettings())
    if not webhook_settings.enabled:
        raise HTTPException(status_code=503, detail="webhooks disabled")

    source = _webhook_sources.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"webhook source {source_id!r} not configured")

    body = await request.body()
    if len(body) > webhook_settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="webhook body too large")

    sig_header = request.headers.get("x-hub-signature-256")
    if not wr.verify_signature(source.secret, body, sig_header):
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}

    text = wr.extract_message(source.message_template, payload)

    async def _noop_reply(_: str) -> None:
        pass

    msg = NormalizedMessage(
        platform="webhook",
        session_id=f"webhook-{source_id}",
        user_id=source.user_id,
        text=text,
        attachments=[],
        reply_func=_noop_reply,
        channel_id="",
    )
    asyncio.create_task(route(msg))
    return Response(status_code=202)
