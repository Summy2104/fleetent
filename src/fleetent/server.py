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

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from fleetent import agent_config, user_store
from fleetent.auth import seed_builtin_admin
from fleetent.config import Settings, WebhooksSettings, configure_logging
from fleetent.cron_scheduler import CronScheduler
from fleetent.governance import quota
from fleetent.governance.permission_gate import (
    _default_gate,
    cleanup_stale_approvals,
    list_approvals,
)
from fleetent.im_gateway import telegram as telegram_adapter
from fleetent.im_gateway.slack_supervisor import SlackSupervisor
from fleetent.integrations import mcp as mcp_client
from fleetent.integrations.mcp import McpServerConfig
from fleetent.integrations.sandbox import (
    Mode,
    SandboxClient,
    cleanup_orphans,
    load_sandbox_mode,
    resolve_effective_mode,
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
from fleetent.platform.im_gateway_management import im_admin_api, im_connector_manager
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.resource_monitoring import collectors, monitor_admin_api
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.user_management import api_key_store, user_admin_api
from fleetent.runtime import run_stream
from fleetent.session import manager as session_mgr
from fleetent.skills import scan as scan_skills
from fleetent.tools.plugin_loader import expand_plugin_patterns, load_plugins

logger = logging.getLogger(__name__)

_MCP_YAML_PATH: Path = Path("config/mcp.yaml")
_WEBHOOK_YAML_PATH: Path = Path("config/webhooks.yaml")
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


# Owner-level connector manager. Slack is intentionally absent: it is per-agent,
# supervised by `_slack_supervisor` from the agent index (per-agent-slack-connector).
_connector_manager = im_connector_manager.ConnectorManager(
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

    logger.info("admin_login_url url=%s", _admin_login_url(user_admin_api.router.prefix))

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

    # Webhook gating settings (enabled flag + max body size) on app.state, and load
    # sources from config/webhooks.yaml if present (zhangyang's yaml design, kept).
    app.state.webhook_settings = settings.webhooks
    from fleetent import webhook_router as _wr

    _webhook_sources.clear()
    if _WEBHOOK_YAML_PATH.exists():
        _webhook_sources.update(_wr.load_sources(_WEBHOOK_YAML_PATH))

    # IM connectors are driven by the registry via the manager: only enabled platforms
    # with usable config start. Wire the admin-API seams to this running manager so
    # enable/disable endpoints can drive lifecycle without importing the loop.
    loop = asyncio.get_running_loop()
    im_admin_api.start_connector = lambda owner_id, platform: asyncio.run_coroutine_threadsafe(
        _connector_manager.start(owner_id, platform), loop
    ).result()
    im_admin_api.stop_connector = lambda owner_id, platform: asyncio.run_coroutine_threadsafe(
        _connector_manager.stop(owner_id, platform), loop
    ).result()
    await _connector_manager.start_all_enabled()
    # per-agent-slack-connector: one Socket Mode connection per agent declaring
    # connectors.slack, sourced from the agent index scanned above.
    await _slack_supervisor.start_from_index()

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

    for owner_id, platform in list(_connector_manager.running()):
        await _connector_manager.stop(owner_id, platform)
    await _slack_supervisor.stop_all()
    try:
        await cron.shutdown()
    except Exception as exc:
        logger.warning("cron_scheduler_shutdown_failed error=%s", exc)
    await session_mgr.stop_session_maintenance()
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


@app.websocket("/ws")
async def ws_gateway(websocket: WebSocket) -> None:
    """Bidirectional JSON-RPC 2.0 gateway for the terminal TUI (tui-gateway).

    Authenticates the Bearer ``ma-`` key on the handshake, then runs a single
    dispatch over a newline-delimited JSON-RPC protocol. SSE ``/chat`` is unaffected.
    """
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
        await websocket.close(code=1008)  # policy violation: auth required
        return
    user, _key_meta = result

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
                await transport.write(tui_proto.make_error(None, tui_proto.PARSE_ERROR, str(exc)))
                continue
            response = await tui_dispatch.dispatch(conn, request)
            if response is not None:
                await transport.write(response)
    except WebSocketDisconnect:
        pass
    finally:
        # Peer gone / connection closed: cancel in-flight runs and release the socket.
        conn.cancel_all()
        await transport.close()


@app.post("/webhook/{source_id}")
async def webhook(source_id: str, request: Request) -> Response:
    from fleetent import webhook_router as wr
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    # Security gates (adopted from main's design onto the kept yaml source model):
    # reject before any dispatch when webhooks are disabled or the body is oversized.
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
