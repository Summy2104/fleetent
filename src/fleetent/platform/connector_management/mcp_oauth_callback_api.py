"""Public OAuth redirect endpoint for managed per-user MCP authorization (slice 2).

The OAuth provider redirects the authorizing user's browser here (the redirect_uri the
agent put in the authorization link points at this platform route). Identity is recovered
solely from the one-time ``state`` (never from any login session). Mirrors the standalone
agent callback shape so the two deployment modes behave identically.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from fleetent.platform.connector_management import mcp_oauth_service

router = APIRouter()


@router.get("/oauth/callback")
async def oauth_callback(code: str | None = None, state: str | None = None) -> PlainTextResponse:
    outcome = await mcp_oauth_service.complete_callback(code, state)
    if outcome.ok:
        return PlainTextResponse("Authorization complete. You can close this window.")
    return PlainTextResponse(f"Authorization failed: {outcome.status}", status_code=400)
