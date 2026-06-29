"""Per-user api-key credential-submission trigger: secure-form link build + DM delivery.

Sibling to :mod:`authorization` (per-user OAuth). A per-user api-key/bearer server with no
stored ``(user, agent, server)`` key MUST NOT fail or hang: the call returns a "needs
credential" result on the existing degrade chain (handled in ``client.py``) and triggers
delivery of a *secure-form* link to that user. Unlike OAuth there is no PKCE / code
exchange — the user submits their existing key through a fleetent-hosted form whose POST
reverse-resolves the triple from the one-shot ``state`` alone (never a login state).

This module reuses the OAuth slice's shared seams rather than duplicating them:

* the process-level :class:`~fleetent.integrations.mcp.oauth_authcode.StateStore`
  (:func:`authorization.get_oauth_state_store`) — the one-shot, short-TTL, unguessable
  ``state`` bound to ``(user, agent, server)``; the PKCE ``verifier`` field is unused for a
  credential submission and left empty.
* the authorization-link *deliverer* seam
  (:func:`authorization.get_authorization_link_deliverer`) — the same per-call / boot DM
  deliverer the OAuth path uses; only the URL differs (it points at the credential form).
* the shared public base (:func:`authorization.public_base`) — the form is hosted on the
  same agent base as the OAuth callback.

It imports only sibling MCP modules; no platform / outbound import, and holds no live
resource at module scope (state store and deliverer are injectable references).
"""

from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import urljoin

from fleetent.integrations.mcp import authorization as _authz

logger = logging.getLogger(__name__)

# Path the standalone agent (and managed platform) mount the credential form at.
CREDENTIAL_PATH = "/mcp/credential"


def render_credential_form(state: str) -> str:
    """Render the minimal credential-submission form carrying a one-shot ``state``.

    Shared by both deployment modes (standalone agent + managed platform host the same
    form). A single masked ``key`` input plus the ``state`` as a hidden field (the one-shot
    CSRF token); the key is never pre-filled or echoed. Posts back to the same path.

    Args:
        state: The one-shot state token binding this form to a (user, agent, server) triple.

    Returns:
        A self-contained HTML page (no external assets).
    """
    safe_state = html.escape(state, quote=True)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Provide your API key</title></head><body>"
        "<h2>Provide your API key</h2>"
        "<p>Paste your key below. It is stored encrypted and never shown in the chat.</p>"
        f"<form method='post' action='{CREDENTIAL_PATH}'>"
        f"<input type='hidden' name='state' value='{safe_state}'>"
        "<input type='password' name='key' autocomplete='off' "
        "placeholder='your api key' required style='width:100%;padding:8px'>"
        "<button type='submit' style='margin-top:8px;padding:8px 16px'>Submit</button>"
        "</form></body></html>"
    )


def credential_form_uri(state: str) -> str:
    """Assemble the credential-form URL carrying a one-shot ``state``.

    ``<public base> + /mcp/credential?state=<state>`` (the same agent base as the OAuth
    callback). Falls back to the bare path when no public base is configured (localhost dev /
    same-origin). A trailing slash on the base is handled by ``urljoin``.

    Args:
        state: The one-shot state token binding the form to the (user, agent, server) triple.

    Returns:
        The fully-qualified form URL to deliver to the user.
    """
    base = _authz.public_base()
    if not base:
        url = CREDENTIAL_PATH
    else:
        url = str(urljoin(base if base.endswith("/") else base + "/", CREDENTIAL_PATH.lstrip("/")))
    return f"{url}?state={state}"


def build_credential_link(server: Any, user_id: str, agent_id: str) -> str:
    """Build a secure-form submission link bound to ``(user, agent, server)``.

    Issues a one-shot, TTL-bounded ``state`` in the shared state store (the PKCE verifier is
    unused for credentials → empty string) and returns the form URL carrying it. The form's
    POST reverse-resolves the triple from ``state`` alone, so the link is the only capability
    the user needs — hence DM-only, short-TTL, one-shot delivery.

    Args:
        server: The per-user api-key server config (only ``id`` is read).
        user_id: The requesting message sender's principal user id.
        agent_id: The agent id completing the isolation triple.

    Returns:
        The fully-assembled credential-form URL to deliver to the user.
    """
    state = _authz.get_oauth_state_store().issue(user_id, agent_id, server.id, "")
    return credential_form_uri(state)


async def emit_credential_link(server: Any, user_id: str, agent_id: str) -> bool:
    """Build a credential link for the triple and deliver it via the wired deliverer.

    Always builds the link (issuing the bound state); delivery is best-effort through the
    injected deliverer (the same seam as OAuth). A missing deliverer or a delivery failure is
    logged and returns False — it never raises, so the caller can still return a "needs
    credential" result on the degrade chain.

    Args:
        server: The per-user api-key server config.
        user_id: The requesting user id.
        agent_id: The agent id completing the isolation triple.

    Returns:
        True iff the link was delivered to the user (e.g. DM'd); False otherwise.
    """
    url = build_credential_link(server, user_id, agent_id)
    deliverer = _authz.get_authorization_link_deliverer()
    if deliverer is None:
        logger.info("mcp_cred_link_no_deliverer server_id=%s user_id=%s", server.id, user_id)
        return False
    try:
        return await deliverer(user_id, agent_id, server.id, url)
    except Exception as exc:  # noqa: BLE001 — delivery is best-effort; never crash the call
        logger.warning(
            "mcp_cred_link_deliver_failed server_id=%s user_id=%s error=%s",
            server.id,
            user_id,
            exc,
        )
        return False
