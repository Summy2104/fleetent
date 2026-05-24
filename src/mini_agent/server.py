"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mini_agent import mcp_client
from mini_agent.agent_loop import run_stream
from mini_agent.config import Settings
from mini_agent.mcp_client import McpServerConfig
from mini_agent.permission_gate import _default_gate
from mini_agent.skill_registry import scan as scan_skills
from mini_agent.user_store import get_by_api_key

logger = logging.getLogger(__name__)

_MCP_YAML_PATH: Path = Path("config/mcp.yaml")


async def _start_slack_adapter(app_token: str) -> None:
    """Start Slack Socket Mode adapter as a background task."""
    try:
        from typing import Any

        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        from mini_agent.im_gateway.slack import create_app as create_slack_app

        slack_app: Any = create_slack_app()
        handler = AsyncSocketModeHandler(slack_app, app_token)
        await handler.start_async()  # type: ignore[no-untyped-call]
    except Exception as exc:
        logger.warning("slack_adapter_start_failed error=%s", exc)


async def _start_telegram_adapter() -> None:
    """Start Telegram polling adapter as a background task."""
    try:
        from typing import Any

        from mini_agent.im_gateway.telegram import create_app as create_telegram_app

        tg_app: Any = create_telegram_app()
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()
    except Exception as exc:
        logger.warning("telegram_adapter_start_failed error=%s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scan_skills()
    settings = Settings()

    # Load MCP servers from config/mcp.yaml if present
    if _MCP_YAML_PATH.exists():
        try:
            raw = yaml.safe_load(_MCP_YAML_PATH.read_text())
            servers = [McpServerConfig(**s) for s in raw.get("servers", [])]
            await mcp_client.register_all(servers)
        except Exception as exc:
            logger.warning("mcp_yaml_load_failed path=%s error=%s", _MCP_YAML_PATH, exc)

    # Start IM adapters as background tasks if tokens are configured
    if settings.slack_bot_token and settings.slack_app_token:
        asyncio.create_task(_start_slack_adapter(settings.slack_app_token))

    if settings.telegram_bot_token:
        asyncio.create_task(_start_telegram_adapter())

    yield


app = FastAPI(title="mini-agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


async def _require_auth(authorization: str = Header()) -> str:
    """Extract user_id from Bearer token. Raises 401 if invalid."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    user = get_by_api_key(api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user.id


@app.get("/health")
async def health() -> dict:  # type: ignore[type-arg]
    settings = Settings()
    return {
        "status": "ok",
        "adapters": {
            "slack": bool(settings.slack_bot_token),
            "telegram": bool(settings.telegram_bot_token),
        },
    }


class ApprovalRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    approver_user_id: str = "anonymous"


@app.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, req: ApprovalRequest) -> dict:  # type: ignore[type-arg]
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
    await _default_gate.resolve(
        approval_id=approval_id,
        decision=req.decision,  # type: ignore[arg-type]
        approver_user_id=req.approver_user_id,
    )
    return {"status": "ok", "approval_id": approval_id, "decision": req.decision}


@app.post("/chat")
async def chat(
    req: ChatRequest, user_id: str = Depends(_require_auth)
) -> StreamingResponse:
    async def _stream() -> AsyncGenerator[str, None]:
        try:
            async for event in run_stream(req.message, user_id=user_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
