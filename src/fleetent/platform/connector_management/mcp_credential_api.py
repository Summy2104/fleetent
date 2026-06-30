"""Public credential-submission endpoint for managed per-user MCP api-key (slice apikey 4.2).

The user opens a fleetent-hosted form (the link the agent DM'd points at this platform
route) and submits their own api-key/bearer. Identity is recovered solely from the one-time
``state`` (registered by the agent through the node loopback, reusing the pending store),
never from any login session — the end user has no fleetent account. Mirrors the standalone
agent form (:mod:`fleetent.integrations.mcp.standalone_credential`) so the two deployment
modes behave identically. The plaintext key is encrypted at the store boundary and never
echoed back.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from fleetent.integrations.mcp.credential_submission import render_credential_form
from fleetent.platform.connector_management import mcp_oauth_service

router = APIRouter()


@router.get("/mcp/credential")
async def credential_form(state: str | None = None) -> HTMLResponse:
    """Render the managed credential-submission form for a one-shot ``state``.

    The state is validated only on POST (it is not consumed by rendering). A missing state
    is a bad request.
    """
    if not state:
        raise HTTPException(status_code=400, detail="missing state")
    return HTMLResponse(render_credential_form(state))


@router.post("/mcp/credential")
async def credential_submit(state: str = Form(...), key: str = Form(...)) -> PlainTextResponse:
    """Store the submitted key under the state's triple as a static credential.

    An invalid / expired / already-used ``state`` is rejected with 400 and nothing is
    written; the key is never echoed back.
    """
    outcome = mcp_oauth_service.complete_credential_submit(state, key)
    if outcome.ok:
        return PlainTextResponse("Credential saved. You can close this window.")
    return PlainTextResponse(f"Submission failed: {outcome.status}", status_code=400)
