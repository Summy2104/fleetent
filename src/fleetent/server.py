"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from fleetent import api_key_store, mcp_client, quota, session_mgr, user_admin_api, user_store
from fleetent.auth import seed_builtin_admin
from fleetent.cron_scheduler import CronScheduler
from fleetent.agent_loop import run_stream
from fleetent.config import Settings
from fleetent.mcp_client import McpServerConfig
from fleetent.permission_gate import _default_gate, cleanup_stale_approvals, list_approvals
from fleetent.sandbox_cleanup import cleanup_orphans
from fleetent.sandbox_client import SandboxClient
from fleetent.plugin_loader import expand_plugin_patterns, load_plugins
from fleetent.sandbox_enablement import Mode, load_sandbox_mode, resolve_effective_mode
from fleetent.skill_registry import scan as scan_skills

logger = logging.getLogger(__name__)

_MCP_YAML_PATH: Path = Path("config/mcp.yaml")
_WEBHOOK_YAML_PATH: Path = Path("config/webhooks.yaml")
_webhook_sources: dict[str, Any] = {}


async def _start_slack_adapter(app_token: str) -> None:
    """Start Slack Socket Mode adapter as a background task."""
    try:
        from typing import Any

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
        from typing import Any

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
    # AR7: load enabled plugins once at startup (same lifecycle as scan_skills /
    # mcp register_all). A missing plugins/ dir or a bad plugin never aborts boot.
    load_plugins()
    cleanup_stale_approvals()
    settings = Settings()

    # SB3: probe Docker once at startup, resolve the effective code-execution mode,
    # and stash it on app.state for /chat and /health. Docker unavailable degrades
    # the mode to off without blocking startup (the probe itself never raises).
    configured_mode = load_sandbox_mode()
    sandbox_client = SandboxClient()
    docker_available = await sandbox_client.docker_available()
    effective_mode = resolve_effective_mode(configured_mode, docker_available)
    app.state.sandbox_mode = effective_mode
    app.state.sandbox_docker_available = docker_available
    if docker_available:
        logger.info("sandbox_mode_effective mode=%s", effective_mode.value)
    else:
        logger.warning(
            "sandbox_mode_effective mode=%s (docker unavailable; configured=%s)",
            effective_mode.value,
            configured_mode.value,
        )

    # SB8: reuse the single SB3 Docker probe above — when Docker is available,
    # reclaim orphan sandbox-* containers left by a previous crash. Best-effort:
    # a failure is logged and startup proceeds; unavailable Docker skips cleanup
    # (the mode is already degraded by SB3). No second probe, no scheduler.
    if docker_available:
        try:
            await cleanup_orphans(sandbox_client)
        except Exception as exc:
            logger.warning("sandbox_orphan_cleanup_failed error=%s", exc)

    # Seed the built-in admin on first boot; log the one-time initial password.
    admin_seed = seed_builtin_admin()
    if admin_seed is not None:
        admin_user, temp_password = admin_seed
        logger.warning(
            "builtin_admin_seeded username=%s initial_password=%s (must change on first login)",
            admin_user.name,
            temp_password,
        )

    # Load MCP servers from config/mcp.yaml if present
    if _MCP_YAML_PATH.exists():
        try:
            raw = yaml.safe_load(_MCP_YAML_PATH.read_text())
            servers = [McpServerConfig(**s) for s in raw.get("servers", [])]
            await mcp_client.register_all(servers)
        except Exception as exc:
            logger.warning("mcp_yaml_load_failed path=%s error=%s", _MCP_YAML_PATH, exc)

    # MCP3: start the connection-health monitor (bare asyncio task, not cron_scheduler).
    mcp_client.start_health_monitor()

    # Periodic session maintenance: trigger TTL cleanup + capacity eviction on an
    # interval so idle (no-save) periods are still maintained. Bare asyncio task,
    # deliberately NOT routed through cron_scheduler (lead direction; MCP3 precedent).
    session_mgr.start_session_maintenance()

    # Load webhook sources from config/webhooks.yaml if present
    from fleetent import webhook_router as _wr

    _webhook_sources.clear()
    if _WEBHOOK_YAML_PATH.exists():
        _webhook_sources.update(_wr.load_sources(_WEBHOOK_YAML_PATH))

    # Start IM adapters as background tasks if tokens are configured
    if settings.slack_bot_token and settings.slack_app_token:
        asyncio.create_task(_start_slack_adapter(settings.slack_app_token))

    if settings.telegram_bot_token:
        asyncio.create_task(_start_telegram_adapter())

    cron = CronScheduler()
    await cron.start()

    yield

    await cron.shutdown()
    await session_mgr.stop_session_maintenance()
    await mcp_client.close()


app = FastAPI(title="fleetent", lifespan=lifespan)
app.include_router(user_admin_api.router)


class ChatRequest(BaseModel):
    message: str


async def _authenticate(authorization: str = Header()) -> tuple[user_store.User, dict]:
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


@app.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    auth_result: tuple[user_store.User, dict] = Depends(_authenticate),
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
    # AR7: an agent's plugin allowlist expands to `{name}__*` namespace patterns
    # merged into allowed_tools, so the agent_loop schema filter exposes only the
    # authorised plugins' namespaced tools to the LLM.
    allowed_tools = agent.allowed_tools + expand_plugin_patterns(agent.plugins) if agent else None
    agent_name = agent.name if agent else None
    agent_features = agent.features if agent else None
    # agent-skill-scoping: per-agent skill-catalog narrowing (empty = no narrowing).
    # No bound agent → None → run_stream renders the full catalog (existing behavior).
    allowed_skills = agent.allowed_skills if agent else None
    # SB3: effective mode resolved at startup gates run_code's schema visibility.
    sandbox_mode: Mode = getattr(request.app.state, "sandbox_mode", Mode.OFF)

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
            kwargs: dict[str, Any] = {"user_id": user_id, "sandbox_mode": sandbox_mode}
            if system_prompt is not None:
                kwargs["system_prompt"] = system_prompt
            if allowed_tools is not None:
                kwargs["allowed_tools"] = allowed_tools
            if agent_name is not None:
                kwargs["agent_name"] = agent_name
            if agent_features is not None:
                kwargs["agent_features"] = agent_features
            if allowed_skills is not None:
                kwargs["allowed_skills"] = allowed_skills
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

    source = _webhook_sources.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"webhook source {source_id!r} not configured")

    body = await request.body()
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
