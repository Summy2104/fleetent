"""Per-user OAuth authorization trigger: no-token detection, link build + DM delivery (D8).

When a per-user OAuth (authorization_code) MCP service is called by a user who has no
valid ``(user, agent, server)`` token yet, the call MUST NOT fail or hang: it returns a
"needs authorization" result on the existing degrade chain and triggers delivery of an
authorization link to that user (D8). This module owns the trigger pieces that are
independent of the SDK session machinery in ``client.py``:

* the process-level, injectable :class:`StateStore` seam (default ``InMemoryStateStore``)
  shared with the standalone callback (Group 7);
* :func:`build_authorization_link`, which assembles an OAuth 2.1 Authorization Code +
  PKCE link whose ``state`` is bound to ``(user_id, agent_id, server_id)`` and whose
  ``redirect_uri`` exactly matches the agent's configured callback;
* an injectable authorization-link *deliverer* seam, so ``client.py`` can emit a link
  without importing the IM/outbound layer — standalone boot wires a deliverer that DMs
  the link to the requesting user (never a shared channel, to prevent state theft).

This module imports only sibling MCP modules (``oauth_authcode`` / ``per_user_tokens``);
it does not import the platform package nor the outbound/IM layer, and holds no live
resource at module scope (the state store and the deliverer are injectable references).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any
from urllib.parse import urljoin

from fleetent.integrations.mcp.oauth_authcode import (
    InMemoryStateStore,
    StateStore,
    build_authorization_url,
    generate_pkce,
)

logger = logging.getLogger(__name__)

# Default callback path the standalone agent mounts (Group 7) and the AS redirects to.
_DEFAULT_REDIRECT_PATH = "/oauth/callback"
# Env var holding the public base URL the agent's callback is reachable at, e.g.
# ``https://agent.example.internal``. The redirect_uri is this base + the server's
# redirect_path; it MUST exactly match the value pre-registered at the authorization
# server. Injectable for tests via ``set_redirect_base``.
_REDIRECT_BASE_ENV = "FLEETENT_OAUTH_REDIRECT_BASE"


# ── state store seam (shared with Group 7 callback) ──────────────────────────────
# A process-level, injectable store (not a live resource: an in-memory TTL dict). Boot
# wires one instance here; the standalone callback consumes the *same* instance so a
# state issued at link-build time is consumable at callback time. Tests swap it freely.
_state_store: StateStore = InMemoryStateStore()


def set_oauth_state_store(store: StateStore) -> None:
    """Inject the process-level OAuth state store (shared with the callback, Group 7).

    Called once at agent boot so the link-issuing path and the callback-consuming path
    share one store instance. ``store`` is a TTL-bounded mapping, never a live resource.
    """
    global _state_store
    _state_store = store


def get_oauth_state_store() -> StateStore:
    """Return the process-level OAuth state store (default :class:`InMemoryStateStore`)."""
    return _state_store


def reset_oauth_state_store() -> None:
    """Test hook: restore a fresh default in-memory state store."""
    global _state_store
    _state_store = InMemoryStateStore()


# ── redirect base seam ───────────────────────────────────────────────────────────

_redirect_base_override: str | None = None


def set_redirect_base(base: str | None) -> None:
    """Override the callback public base URL (tests / explicit boot config).

    None reverts to reading :data:`_REDIRECT_BASE_ENV` from the environment.
    """
    global _redirect_base_override
    _redirect_base_override = base


def _redirect_base() -> str:
    """The agent callback's public base URL (override > env > empty)."""
    if _redirect_base_override is not None:
        return _redirect_base_override
    return os.environ.get(_REDIRECT_BASE_ENV, "").strip()


def redirect_uri_for(server: Any) -> str:
    """Assemble the exact ``redirect_uri`` for a per-user oauth server.

    The URI is ``<public base> + <server.redirect_path>`` (defaulting the path to
    ``/oauth/callback``). It MUST match the value registered at the authorization server.
    A trailing slash on the base is handled by ``urljoin``.

    Args:
        server: The per-user oauth server config (carries ``redirect_path``).

    Returns:
        The fully-qualified redirect URI, or just the path when no base is configured
        (same-origin callback; localhost dev).
    """
    path = getattr(server, "redirect_path", "") or _DEFAULT_REDIRECT_PATH
    base = _redirect_base()
    if not base:
        return path
    # urljoin needs the base to end without a path segment being dropped; ensure a slash.
    return str(urljoin(base if base.endswith("/") else base + "/", path.lstrip("/")))


# ── authorization-link delivery seam (no outbound/IM import here) ─────────────────
# An injected coroutine ``(user_id, agent_id, server_id, url) -> bool`` that delivers the
# link to the requesting user (standalone: a DM via the agent's own connector). Returns
# True iff delivered. Left None when no IM delivery path exists (TUI / HTTP); the trigger
# still returns a clear "needs authorization" result rather than crashing.
AuthorizationLinkDeliverer = Callable[[str, str, str, str], Awaitable[bool]]

_deliverer: AuthorizationLinkDeliverer | None = None

# Per-call deliverer, set for the duration of one tool dispatch by the registry site that
# holds the live IM connectors + the requester's conversation address. A ContextVar (not a
# module global) so concurrent calls — each its own asyncio task — never see each other's
# deliverer. Takes precedence over the module-level (boot) deliverer when set.
_call_deliverer: ContextVar[AuthorizationLinkDeliverer | None] = ContextVar(
    "mcp_authz_call_deliverer", default=None
)


def set_authorization_link_deliverer(deliverer: AuthorizationLinkDeliverer | None) -> None:
    """Wire (or clear) the process-level authorization-link deliverer (boot fallback).

    The deliverer belongs to the IM/outbound layer; ``client.py`` only invokes it through
    this seam, keeping the MCP client free of any outbound import. None disables delivery
    (link still built/logged). The per-call deliverer (:func:`bind_call_deliverer`) wins
    when set for the current task.
    """
    global _deliverer
    _deliverer = deliverer


def get_authorization_link_deliverer() -> AuthorizationLinkDeliverer | None:
    """Return the effective deliverer for the current task (per-call > boot), or None."""
    return _call_deliverer.get() or _deliverer


def bind_call_deliverer(deliverer: AuthorizationLinkDeliverer | None) -> Any:
    """Bind a per-call deliverer for the current task; returns a ContextVar reset token.

    The dispatch site (which has the live connectors + the requester address) sets a
    closure here for one tool call and resets it afterwards via the returned token, so the
    MCP client can DM the link without the connectors ever being threaded down to it.
    """
    return _call_deliverer.set(deliverer)


def reset_call_deliverer(token: Any) -> None:
    """Reset the per-call deliverer using a token from :func:`bind_call_deliverer`."""
    _call_deliverer.reset(token)


# ── link build ───────────────────────────────────────────────────────────────────


def build_authorization_link(server: Any, user_id: str, agent_id: str) -> str:
    """Build a per-user OAuth 2.1 Authorization Code + PKCE link bound to the triple.

    Generates a fresh PKCE pair, issues a one-shot TTL-bounded ``state`` in the
    process-level store bound to ``(user_id, agent_id, server_id)`` plus the verifier
    (so the callback reverse-resolves identity from ``state`` alone), and assembles the
    authorization URL with the server's ``authorization_endpoint`` / ``client_id`` /
    ``scope`` and the exact configured ``redirect_uri``.

    Args:
        server: The per-user oauth server config.
        user_id: The requesting message sender's principal user id.
        agent_id: The agent id completing the isolation triple.

    Returns:
        The fully-assembled authorization URL to deliver to the user.
    """
    pkce = generate_pkce()
    state = _state_store.issue(user_id, agent_id, server.id, pkce.verifier)
    return build_authorization_url(
        authorization_endpoint=server.authorization_endpoint,
        client_id=server.client_id,
        redirect_uri=redirect_uri_for(server),
        scope=server.scope,
        state=state,
        code_challenge=pkce.challenge,
    )


# ── trigger ────────────────────────────────────────────────────────────────────


async def emit_authorization_link(server: Any, user_id: str, agent_id: str) -> bool:
    """Build a link for ``(user, agent, server)`` and deliver it via the wired deliverer.

    Always builds the link (issuing the bound state); delivery is best-effort through the
    injected deliverer. A missing deliverer or a delivery failure is logged and returns
    False — it never raises, so the caller can still return a "needs authorization"
    result on the degrade chain.

    Args:
        server: The per-user oauth server config.
        user_id: The requesting user id.
        agent_id: The agent id completing the isolation triple.

    Returns:
        True iff the link was delivered to the user (e.g. DM'd); False otherwise.
    """
    url = build_authorization_link(server, user_id, agent_id)
    deliverer = get_authorization_link_deliverer()
    if deliverer is None:
        logger.info("mcp_authz_link_no_deliverer server_id=%s user_id=%s", server.id, user_id)
        return False
    try:
        return await deliverer(user_id, agent_id, server.id, url)
    except Exception as exc:  # noqa: BLE001 — delivery is best-effort; never crash the call
        logger.warning(
            "mcp_authz_link_deliver_failed server_id=%s user_id=%s error=%s",
            server.id,
            user_id,
            exc,
        )
        return False
