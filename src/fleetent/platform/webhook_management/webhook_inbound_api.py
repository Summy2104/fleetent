"""Public managed inbound webhook edge: POST /webhook/{source_id} (live-webhooks).

Looks up the source in the management DB, applies the deployment webhook policy (enabled /
body size), verifies HMAC against the decrypted secret, then forwards the request to the target
agent through the node channel — the agent runs it as the source's user and (optionally) DMs the
result to ``reply_target``. The forward runs in a background task after an immediate 202.

The ``_forward`` seam is wired in ``server.py`` to the real node transport; tests replace it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from fleetent import agent_store, webhook_router
from fleetent.platform.webhook_management import webhook_source_store as store

router = APIRouter()
logger = logging.getLogger(__name__)

# Deployment-level body-size cap for the managed inbound edge. Webhook policy was dissolved from
# platform Settings (config consolidation); per-source enablement lives on each DB row instead.
MAX_BODY_BYTES = 1_048_576


async def _forward_unwired(
    *, agent_name: str, source_id: str, body: bytes, source_meta: str
) -> None:
    logger.warning(
        "webhook forward seam not wired; dropping webhook source_id=%s agent=%s",
        source_id,
        agent_name,
    )


# Wired in server.py to the node transport. Signature: forward the verified webhook to the agent.
_forward: Callable[..., Awaitable[None]] = _forward_unwired


@router.post("/webhook/{source_id}", status_code=202)
async def inbound_webhook(
    source_id: str,
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),  # noqa: B008
) -> dict[str, str]:
    src = store.get_source(source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="unknown webhook source")
    if not src.enabled:
        raise HTTPException(status_code=403, detail="webhooks disabled")

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    if not webhook_router.verify_signature(src.secret, body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="invalid signature")
    if src.agent_id is None:
        raise HTTPException(status_code=409, detail="webhook source has no target agent")
    agent = agent_store.get_by_id(src.agent_id)
    if agent is None:
        raise HTTPException(status_code=409, detail="webhook source target agent not found")
    agent_name = agent.name

    source_meta = json.dumps(
        {
            "user_id": src.user_id,
            "agent_name": agent_name,
            "message_template": src.message_template,
            "reply_target": src.reply_target,
        }
    )

    async def _do_forward() -> None:
        try:
            await _forward(
                agent_name=agent_name,
                source_id=source_id,
                body=body,
                source_meta=source_meta,
            )
        except Exception:  # noqa: BLE001 — best-effort; 202 already returned
            logger.exception("webhook forward failed for source_id=%s", source_id)

    background.add_task(_do_forward)
    return {"status": "accepted", "source_id": source_id}
