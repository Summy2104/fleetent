"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from fleetent import api_key_store, mcp_client, quota, user_admin_api, user_store
from fleetent.agent_loop import run_stream
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, WebhooksSettings, configure_logging, load_mcp_server_settings
from fleetent.cron_scheduler import CronScheduler
from fleetent.mcp_client import McpServerConfig
from fleetent.model_router import ROUTES
from fleetent.observability.startup_diagnostics import (
    diagnose_database_writable,
    diagnose_provider_keys,
    log_config_failed,
    log_config_loaded,
)
from fleetent.permission_gate import _default_gate, cleanup_stale_approvals, list_approvals
from fleetent.skill_registry import scan as scan_skills

logger = logging.getLogger(__name__)

LEGACY_MCP_CONFIG_PATH: Path = Path("config/mcp.yaml")
LEGACY_WEBHOOK_CONFIG_PATH: Path = Path("config/webhooks.yaml")
_webhook_sources: dict[str, Any] = {}


async def _start_slack_adapter(app_token: str) -> None:
    """Start Slack Socket Mode adapter as a background task."""
    try:
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        from fleetent.im_gateway.slack import create_app as create_slack_app

        slack_app: Any = create_slack_app()
        handler = AsyncSocketModeHandler(slack_app, app_token)
        await handler.start_async()  # type: ignore[no-untyped-call]
    except Exception as exc:
        logger.warning("slack_adapter_start_failed error=%s", exc)


async def _start_telegram_adapter() -> None:
    """Start Telegram polling adapter as a background task."""
    try:
        from fleetent.im_gateway.telegram import create_app as create_telegram_app

        tg_app: Any = create_telegram_app()
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()
    except Exception as exc:
        logger.warning("telegram_adapter_start_failed error=%s", exc)


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

    # Start IM adapters as background tasks if tokens are configured
    if settings.slack_bot_token and settings.slack_app_token:
        asyncio.create_task(_start_slack_adapter(settings.slack_app_token))

    if settings.telegram_bot_token:
        asyncio.create_task(_start_telegram_adapter())

    cron = CronScheduler(settings=settings.scheduling)
    await cron.start()

    yield

    await cron.shutdown()
    await mcp_client.close()


app = FastAPI(title="fleetent", lifespan=lifespan)
app.include_router(user_admin_api.router)


class ChatRequest(BaseModel):
    message: str


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
    from fleetent.im_gateway.normalizer import get_agent_for_context

    user, key_meta = auth_result
    user_id = user.id

    agent = get_agent_for_context(
        platform=x_platform or "",
        channel_id=x_channel_id or "",
        user_id=user_id,
    )
    system_prompt = agent.system_prompt if agent else None
    allowed_tools = agent.allowed_tools if agent else None
    agent_name = agent.name if agent else None

    # API-key scope: the key may be restricted to specific agents.
    if agent_name is not None and not api_key_store.check_scope(key_meta["scope"], agent_name):
        raise HTTPException(status_code=403, detail="scope does not allow this agent")

    # Usage quota: reject when the user's or global limit is already exhausted.
    if not quota.check_quota(user_id):
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
            if allowed_tools is not None:
                kwargs["allowed_tools"] = allowed_tools
            if agent_name is not None:
                kwargs["agent_name"] = agent_name
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
