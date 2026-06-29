"""Managed per-user MCP OAuth wiring (slice 2, agent side).

When the agent runs under a node (``FLEETENT_NODE_LOOPBACK_URL`` set), it cannot host its
own callback or hold platform credentials. Instead it sources per-user tokens, and
registers pending authorizations, through a same-host loopback channel on its node — the
node forwards to platform holding the service key. This module injects, into slice-1's
existing seams, a managed token resolver (with an in-process short-TTL cache) and a
managed OAuth state store; standalone leaves these unset and falls back to the local store.

No platform import: the only outbound dependency is the node loopback URL, authenticated
with the agent's own TUI token. The resolver/state-store seams are synchronous, so the
loopback calls here are synchronous ``httpx`` requests to the local node.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

import httpx

from fleetent.integrations.mcp import authorization as _authz
from fleetent.integrations.mcp.oauth_authcode import AuthState
from fleetent.integrations.mcp.per_user_tokens import (
    UserToken,
    set_credential_writer,
    set_user_token_resolver,
)
from fleetent.structured_logging import get_logger

_logger = get_logger("mcp.managed_oauth")

# How long the agent reuses a node-fetched access token before re-fetching. The platform
# refreshes underneath, so a short window bounds staleness without per-request round-trips.
_CACHE_TTL_SECONDS = 50.0


class ManagedUserTokenResolver:
    """Resolve per-user tokens via the node loopback, cached in-process by triple.

    Returns a :class:`UserToken` carrying only the access token (refresh_token=None): the
    refresh token never leaves platform. Returns None when no token is stored (drives
    re-authorization) — the agent's per-request getter re-resolves, so a refresh on the
    platform side surfaces on the next cache miss.
    """

    def __init__(
        self,
        loopback_url: str,
        agent_name: str,
        tui_token: str,
        *,
        now: Callable[[], float] = time.time,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._base = loopback_url.rstrip("/")
        self._agent_name = agent_name
        self._tui_token = tui_token
        self._now = now
        self._post = http_post or self._default_post
        self._cache: dict[tuple[str, str, str], tuple[str, float]] = {}

    def _default_post(self, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.post(url, **kwargs)

    def __call__(self, server_id: str, user_id: str, agent_id: str | None) -> UserToken | None:
        key = (server_id, user_id, agent_id or "")
        cached = self._cache.get(key)
        now = self._now()
        if cached is not None and now < cached[1]:
            return UserToken(cached[0], None, cached[1], None)
        url = f"{self._base}/agent/{self._agent_name}/mcp/oauth-token"
        try:
            resp = self._post(
                url,
                json={"user_id": user_id, "agent_id": agent_id or "", "server_id": server_id},
                headers={"Authorization": f"Bearer {self._tui_token}"},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            _logger.warn("managed_token_fetch_failed", server_id=server_id, error=str(exc))
            return UserToken(cached[0], None, cached[1], None) if cached is not None else None
        if resp.status_code == 404:
            self._cache.pop(key, None)
            return None
        if resp.status_code >= 400:
            _logger.warn("managed_token_fetch_status", server_id=server_id, status=resp.status_code)
            return None
        access = str(resp.json().get("access_token", ""))
        if not access:
            return None
        expires_at = now + _CACHE_TTL_SECONDS
        self._cache[key] = (access, expires_at)
        return UserToken(access, None, expires_at, None)

    def invalidate(self, server_id: str, user_id: str, agent_id: str | None) -> None:
        self._cache.pop((server_id, user_id, agent_id or ""), None)


class ManagedStateStore:
    """OAuth state store that registers pending-auth on platform via the node loopback.

    ``issue`` generates a one-time state, looks up the server's OAuth config + redirect_uri
    locally, and posts the full pending record (state→verifier/triple/config) to the node,
    which forwards it to platform. ``consume`` is never used agent-side under managed
    deployment (platform's callback consumes the state), so it returns None.
    """

    def __init__(
        self,
        loopback_url: str,
        agent_name: str,
        tui_token: str,
        server_lookup: Callable[[str], Any | None],
        *,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._base = loopback_url.rstrip("/")
        self._agent_name = agent_name
        self._tui_token = tui_token
        self._server_lookup = server_lookup
        self._post = http_post or (lambda url, **kw: httpx.post(url, **kw))

    def issue(self, user_id: str, agent_id: str, server_id: str, verifier: str) -> str:
        state = secrets.token_urlsafe(32)
        server = self._server_lookup(server_id)
        # McpServerConfig flattens the OAuth fields onto itself (see client.from_settings),
        # and redirect_uri_for reads server.redirect_path — read them the same way.
        token_url = getattr(server, "token_url", "") if server is not None else ""
        client_id = getattr(server, "client_id", "") if server is not None else ""
        client_secret_env = getattr(server, "client_secret_env", "") if server is not None else ""
        redirect_uri = _authz.redirect_uri_for(server) if server is not None else ""
        self._post(
            f"{self._base}/agent/{self._agent_name}/mcp/oauth-pending",
            json={
                "state": state,
                "code_verifier": verifier,
                "user_id": user_id,
                "agent_id": agent_id,
                "server_id": server_id,
                "token_url": token_url,
                "client_id": client_id,
                "client_secret_env": client_secret_env,
                "redirect_uri": redirect_uri,
            },
            headers={"Authorization": f"Bearer {self._tui_token}"},
            timeout=10.0,
        )
        return state

    def consume(self, state: str) -> AuthState | None:
        return None


class ManagedCredentialWriter:
    """Persist a user-supplied static api-key via the node loopback (mode 2 tool, managed).

    Posts the (triple, key) to the node's ``credential-set`` loopback, which forwards to
    platform holding the service key — the agent never imports/addresses platform. Returns
    whether the write succeeded so the tool can report a clean failure. The form path uses a
    one-shot state instead; this direct write is only for the in-DM tool, where the agent
    already knows the calling user.
    """

    def __init__(
        self,
        loopback_url: str,
        agent_name: str,
        tui_token: str,
        *,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._base = loopback_url.rstrip("/")
        self._agent_name = agent_name
        self._tui_token = tui_token
        self._post = http_post or (lambda url, **kw: httpx.post(url, **kw))

    def __call__(self, server_id: str, user_id: str, agent_id: str | None, key: str) -> bool:
        try:
            resp = self._post(
                f"{self._base}/agent/{self._agent_name}/mcp/credential-set",
                json={
                    "user_id": user_id,
                    "agent_id": agent_id or "",
                    "server_id": server_id,
                    "key": key,
                },
                headers={"Authorization": f"Bearer {self._tui_token}"},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            _logger.warn("managed_credential_set_failed", server_id=server_id, error=str(exc))
            return False
        return resp.status_code < 400


def wire_managed_oauth(
    loopback_url: str,
    agent_name: str,
    tui_token: str,
    server_lookup: Callable[[str], Any | None],
) -> ManagedUserTokenResolver:
    """Inject the managed token resolver + state store + credential writer onto slice seams."""
    resolver = ManagedUserTokenResolver(loopback_url, agent_name, tui_token)
    set_user_token_resolver(resolver)
    _authz.set_oauth_state_store(
        ManagedStateStore(loopback_url, agent_name, tui_token, server_lookup)
    )
    set_credential_writer(ManagedCredentialWriter(loopback_url, agent_name, tui_token))
    return resolver
