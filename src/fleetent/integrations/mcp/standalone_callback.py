"""Standalone self-hosted OAuth callback + transparent token refresh (Group 7, D6/D7).

In a standalone deployment (no platform) the agent self-hosts the OAuth redirect endpoint
and a per-user token store, closing the Authorization Code loop entirely on the agent side:

* :func:`handle_oauth_callback` consumes the one-shot ``state`` from the shared state store
  (Group 6) to reverse-resolve ``(user_id, agent_id, server_id)`` + the PKCE verifier —
  identity comes *only* from ``state``, never from the callback request's login state — then
  exchanges the ``code`` for tokens via :mod:`oauth_authcode` and persists them, encrypted,
  in the local per-user token store. An unknown / expired / already-consumed ``state`` is
  rejected with no token exchange and no write.
* :func:`build_standalone_token_refresher` returns the transparent refresher wired into the
  client seam (:func:`client.set_token_refresher`): when a per-user call meets an expired but
  refreshable token, it refreshes via :mod:`oauth_authcode`, writes the rotated token back to
  the local store, and returns it — so refresh is transparent to the caller. A genuine auth
  failure clears the bad token and returns None so the call degrades to "needs authorization".

This module imports only sibling MCP modules + the agent-side secret/HTTP helpers; it never
imports the platform package (agent runtime stays decoupled per the architecture contract)
and holds no live resource at module scope (the store handle and HTTP client are passed in /
created per call).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from fleetent.integrations.mcp import authorization as _authz
from fleetent.integrations.mcp import client as _client
from fleetent.integrations.mcp.client import McpServerConfig, find_registered_server
from fleetent.integrations.mcp.oauth_authcode import (
    OAuthAuthError,
    OAuthTransientError,
    TokenResult,
    exchange_code,
    refresh_token,
)
from fleetent.integrations.mcp.per_user_tokens import UserToken, UserTokenStore
from mcp.shared._httpx_utils import create_mcp_http_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallbackResult:
    """Outcome of handling an OAuth redirect callback.

    Attributes:
        ok: True iff the code was exchanged and a token was stored.
        status: A short machine-readable status (``stored`` / ``invalid_state`` /
            ``unknown_server`` / ``exchange_failed``).
        detail: A human-readable, log/page-safe description (never carries secrets).
    """

    ok: bool
    status: str
    detail: str


def _client_secret_for(server: McpServerConfig) -> str:
    """Read the server's OAuth client secret from its configured env var (never inline)."""
    return os.environ.get(server.client_secret_env, "") if server.client_secret_env else ""


def _to_user_token(result: TokenResult) -> UserToken:
    """Project a protocol-level :class:`TokenResult` onto the stored :class:`UserToken`."""
    return UserToken(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_at=result.expires_at,
        scope=result.scope,
    )


async def handle_oauth_callback(
    *,
    code: str | None,
    state: str | None,
    store: UserTokenStore,
    http_client: httpx.AsyncClient | None = None,
    now: Callable[[], float] = time.time,
) -> CallbackResult:
    """Complete a standalone OAuth Authorization Code callback (Group 7, 7.2).

    Identity is reverse-resolved from ``state`` alone (consumed one-shot from the shared
    state store): an unknown / expired / already-consumed ``state`` — or a missing ``code``
    — is rejected without any token exchange or write. On a valid state the server config is
    resolved by id, the ``code`` is exchanged (with the bound PKCE verifier + exact
    redirect_uri), and the resulting token is stored under the ``(user, agent, server)``
    triple from the state. The callback request's own login state is never consulted.

    Args:
        code: The ``code`` query parameter from the redirect.
        state: The ``state`` query parameter from the redirect.
        store: The local per-user token store to persist the exchanged token into.
        http_client: An async HTTP client for the token endpoint; one is created (with the
            MCP defaults) when omitted, and closed before returning.
        now: Time source for computing token expiry; defaults to ``time.time``.

    Returns:
        A :class:`CallbackResult` describing the outcome (never raises on the OAuth/HTTP
        failure paths — they map to an ``ok=False`` result the endpoint renders as a 4xx).
    """
    if not state or not code:
        return CallbackResult(ok=False, status="invalid_state", detail="missing code or state")
    auth_state = _authz.get_oauth_state_store().consume(state)
    if auth_state is None:
        # Unknown / expired / already-consumed: reject, no exchange, no token write.
        logger.info("mcp_oauth_callback_rejected reason=invalid_state")
        return CallbackResult(
            ok=False, status="invalid_state", detail="invalid, expired, or already-used state"
        )
    server = find_registered_server(auth_state.server_id)
    if server is None:
        logger.warning("mcp_oauth_callback_unknown_server server_id=%s", auth_state.server_id)
        return CallbackResult(
            ok=False, status="unknown_server", detail="unknown server for this authorization"
        )

    owns_client = http_client is None
    client = http_client or create_mcp_http_client()
    try:
        result = await exchange_code(
            token_url=server.token_url,
            client_id=server.client_id,
            client_secret=_client_secret_for(server),
            code=code,
            code_verifier=auth_state.verifier,
            redirect_uri=_authz.redirect_uri_for(server),
            http_client=client,
            now=now,
        )
    except (OAuthAuthError, OAuthTransientError) as exc:
        # A consumed-but-failed state cannot be reused (one-shot): the user must restart the
        # flow. Surfaced as a clean failure result, never an unhandled 500.
        logger.warning("mcp_oauth_callback_exchange_failed server_id=%s error=%s", server.id, exc)
        return CallbackResult(ok=False, status="exchange_failed", detail="token exchange failed")
    finally:
        if owns_client:
            await client.aclose()

    store.put(auth_state.user_id, auth_state.agent_id, server.id, _to_user_token(result))
    logger.info(
        "mcp_oauth_callback_stored server_id=%s user_id=%s agent_id=%s",
        server.id,
        auth_state.user_id,
        auth_state.agent_id,
    )
    return CallbackResult(ok=True, status="stored", detail="authorization complete")


def build_standalone_token_refresher(
    store: UserTokenStore,
    *,
    http_client_factory: Callable[[], httpx.AsyncClient] = create_mcp_http_client,
    now: Callable[[], float] = time.time,
) -> Callable[[str, str, str | None, UserToken], Awaitable[UserToken | None]]:
    """Build the transparent refresher wired into ``client.set_token_refresher`` (7.3, D7).

    The returned coroutine refreshes an expired access token using its refresh token and the
    server's OAuth config (resolved from the live registry; secret from its configured env
    var), writes the rotated token back to ``store`` (so the live per-user session's per-
    request bearer / a stdio re-spawn picks it up transparently), and returns it. A genuine
    auth failure (revoked refresh) clears the bad token and returns None — driving the call
    to "needs authorization". A transient failure keeps the stored token and returns it
    unchanged so the call degrades rather than forcing re-authorization. Never raises.

    Args:
        store: The local per-user token store to read/write rotated tokens.
        http_client_factory: Factory for the token-endpoint HTTP client (injectable/mockable).
        now: Time source for computing the rotated token's expiry.

    Returns:
        An async ``(server_id, user_id, agent_id, token) -> UserToken | None`` refresher.
    """

    async def refresher(
        server_id: str, user_id: str, agent_id: str | None, token: UserToken
    ) -> UserToken | None:
        if token.refresh_token is None:
            return None
        server = find_registered_server(server_id)
        if server is None:
            logger.warning("mcp_token_refresh_unknown_server server_id=%s", server_id)
            return token  # keep the token; the call degrades downstream
        client = http_client_factory()
        try:
            result = await refresh_token(
                token_url=server.token_url,
                client_id=server.client_id,
                client_secret=_client_secret_for(server),
                refresh_token=token.refresh_token,
                http_client=client,
                now=now,
            )
        except OAuthAuthError:
            # Revoked / invalid refresh token: clear it so the next call re-authorizes.
            store.delete(user_id, agent_id or "", server_id)
            logger.info("mcp_token_refresh_revoked server_id=%s user_id=%s", server_id, user_id)
            return None
        except OAuthTransientError as exc:
            logger.warning("mcp_token_refresh_transient server_id=%s error=%s", server_id, exc)
            return token  # keep the stale token; the call degrades, never forces re-auth
        finally:
            await client.aclose()
        refreshed = _to_user_token(result)
        store.put(user_id, agent_id or "", server_id, refreshed)
        logger.info("mcp_token_refreshed server_id=%s user_id=%s", server_id, user_id)
        return refreshed

    return refresher


def wire_standalone_oauth(store: UserTokenStore) -> None:
    """Wire the standalone local token store + transparent refresher at agent boot (7.2/7.3).

    Sets the local per-user token store (so ``resolve_user_token`` reads the encrypted local
    library) and the transparent refresher seam. The shared OAuth *state* store keeps the
    Group 6 default singleton so link-issuing and the callback share one instance. This is a
    pure local wiring (no platform), so it is safe to call unconditionally in a standalone
    boot; managed boot (slice 2) wires its own resolver/refresher instead.
    """
    from fleetent.integrations.mcp.per_user_tokens import set_local_user_token_store

    set_local_user_token_store(store)
    _client.set_token_refresher(build_standalone_token_refresher(store))
