"""Platform-side per-user MCP OAuth machinery (managed slice 2).

Drives the managed token lifecycle on top of the management-DB stores
(``mcp_user_token_store``) and the shared deployment-agnostic protocol logic
(``integrations.mcp.oauth_authcode`` — D6; face→core import is allowed). The agent
initiates authorization (builds the link, sends it) and registers pending-auth through
the node; this service completes the callback exchange, stores tokens, and serves
short-lived access tokens to the node with transparent refresh. refresh_token and
client_secret never leave platform.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from fleetent.integrations.mcp import oauth_authcode
from fleetent.platform.connector_management import mcp_user_token_store as store

# Refresh an access token this many seconds before its stated expiry.
_REFRESH_SKEW_SECONDS = 30.0

# Injected at the composition root (server.py) to resolve a client_secret env reference
# from agent_secrets, mirroring user_store.set_api_key_resolver. Kept as a seam so this
# ②控制-face module does not import the ③编排-face agent_lifecycle (plane boundary). When
# unset (no platform wiring / PKCE public clients), there is no client secret.
_client_secret_resolver: Callable[[int | None, str], str | None] | None = None


def set_client_secret_resolver(resolver: Callable[[int | None, str], str | None] | None) -> None:
    global _client_secret_resolver
    _client_secret_resolver = resolver


@dataclass(frozen=True)
class CallbackOutcome:
    ok: bool
    status: str
    detail: str


def _resolve_client_secret(agent_id: str, client_secret_env: str) -> str:
    """Resolve a client_secret env reference via agent_secrets, best-effort by scope.

    PKCE public clients have no secret (empty env ref -> empty secret). When a ref is set,
    look it up under the agent's scope (agent_id is a string in the runtime triple; numeric
    ids map to the registry agent scope), falling back to the global (None) scope.
    """
    if not client_secret_env or _client_secret_resolver is None:
        return ""
    scoped = int(agent_id) if agent_id.isdigit() else None
    value = _client_secret_resolver(scoped, client_secret_env)
    if value is None and scoped is not None:
        value = _client_secret_resolver(None, client_secret_env)
    return value or ""


def register_pending(
    *,
    state: str,
    code_verifier: str,
    user_id: str,
    agent_id: str,
    server_id: str,
    token_url: str,
    client_id: str,
    client_secret_env: str,
    redirect_uri: str,
    now: float | None = None,
) -> None:
    store.put_pending(
        state=state,
        code_verifier=code_verifier,
        user_id=user_id,
        agent_id=agent_id,
        server_id=server_id,
        token_url=token_url,
        client_id=client_id,
        client_secret_env=client_secret_env,
        redirect_uri=redirect_uri,
        now=now if now is not None else time.time(),
    )


async def complete_callback(
    code: str | None,
    state: str | None,
    *,
    http_client: httpx.AsyncClient | None = None,
    now=time.time,
) -> CallbackOutcome:
    """Complete the authorization-code callback: consume pending, exchange, store token."""
    if not code or not state:
        return CallbackOutcome(False, "invalid_request", "missing code or state")
    pending = store.consume_pending(state, now=now())
    if pending is None:
        return CallbackOutcome(False, "invalid_state", "unknown, expired, or used state")
    client_secret = _resolve_client_secret(pending.agent_id, pending.client_secret_env)
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=30.0)
    try:
        result = await oauth_authcode.exchange_code(
            token_url=pending.token_url,
            client_id=pending.client_id,
            client_secret=client_secret,
            code=code,
            code_verifier=pending.code_verifier,
            redirect_uri=pending.redirect_uri,
            http_client=client,
            now=now,
        )
    except oauth_authcode.OAuthAuthError as exc:
        return CallbackOutcome(False, "exchange_failed", str(exc))
    except oauth_authcode.OAuthTransientError as exc:
        return CallbackOutcome(False, "exchange_transient", str(exc))
    finally:
        if own_client:
            await client.aclose()
    store.put_token(
        pending.user_id,
        pending.agent_id,
        pending.server_id,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_at=result.expires_at,
        scope=result.scope,
        token_url=pending.token_url,
        client_id=pending.client_id,
        client_secret_env=pending.client_secret_env,
    )
    return CallbackOutcome(True, "ok", "authorized")


async def fetch_access_token(
    user_id: str,
    agent_id: str,
    server_id: str,
    *,
    http_client: httpx.AsyncClient | None = None,
    now=time.time,
) -> str | None:
    """Return a currently-valid access token for the triple, refreshing transparently.

    Returns None when no token is stored or a genuine auth failure (revoked refresh) means
    the user must re-authorize. The refresh_token is never returned to the caller.
    """
    token = store.get_token(user_id, agent_id, server_id)
    if token is None:
        return None
    # static credentials (user-supplied api-key/bearer) are never refreshed — return as-is.
    if token.credential_kind == "static":
        return token.access_token
    if token.expires_at is None or token.expires_at - now() > _REFRESH_SKEW_SECONDS:
        return token.access_token
    if not token.refresh_token or not token.token_url:
        # Expired with no way to refresh -> drive re-authorization.
        return None
    client_secret = _resolve_client_secret(agent_id, token.client_secret_env)
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=30.0)
    try:
        result = await oauth_authcode.refresh_token(
            token_url=token.token_url,
            client_id=token.client_id,
            client_secret=client_secret,
            refresh_token=token.refresh_token,
            http_client=client,
            now=now,
        )
    except oauth_authcode.OAuthAuthError:
        # Revoked / invalid refresh -> clear so the next call re-authorizes.
        store.delete_token(user_id, agent_id, server_id)
        return None
    except oauth_authcode.OAuthTransientError:
        # Transient token-endpoint failure -> degrade with the (stale) current token.
        return token.access_token
    finally:
        if own_client:
            await client.aclose()
    store.put_token(
        user_id,
        agent_id,
        server_id,
        access_token=result.access_token,
        refresh_token=result.refresh_token or token.refresh_token,
        expires_at=result.expires_at,
        scope=result.scope or token.scope,
        token_url=token.token_url,
        client_id=token.client_id,
        client_secret_env=token.client_secret_env,
    )
    return result.access_token
