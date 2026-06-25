"""Per-user MCP OAuth token storage abstraction + injectable resolver seam (D5).

per-user OAuth tokens are isolated by the ``(user_id, agent_id, server_id)`` triple
(D1): one agent's user delegation is never reusable by another agent, and the same
user authorizes each agent separately. This module owns:

* :class:`UserToken` — the parsed token record persisted per triple.
* :class:`UserTokenStore` — a storage Protocol with triple-keyed get/put/delete.
* :class:`InMemoryUserTokenStore` — a default in-process store (tests / no-persistence).
* :func:`set_user_token_resolver` / :func:`resolve_user_token` — a module-level
  injectable seam mirroring ``set_im_identity_resolver``: standalone leaves the
  resolver unset and falls back to a local store; managed (slice 2) injects its own
  resolver to source tokens through node→platform.

The seam holds only a *callable reference* (the resolver) and an in-process local
store — never a live DB connection or other long-lived resource — so it does not
violate the owner-task lifecycle rule and introduces no agent→platform import.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UserToken:
    """One per-user OAuth token bound to a ``(user_id, agent_id, server_id)`` triple.

    Attributes:
        access_token: The bearer access token used to authenticate MCP requests.
        refresh_token: The refresh token, if the AS issued one (else None).
        expires_at: Absolute access-token expiry on the issuing clock, or None when
            the AS omitted ``expires_in``.
        scope: The granted scope string, if known (else None).
    """

    access_token: str
    refresh_token: str | None
    expires_at: float | None
    scope: str | None


class UserTokenStore(Protocol):
    """Triple-keyed per-user token store.

    Implementations MUST isolate tokens by the full ``(user_id, agent_id, server_id)``
    triple: a write under one triple MUST NOT be observable under any triple that
    differs in any axis.
    """

    def get(self, user_id: str, agent_id: str, server_id: str) -> UserToken | None:
        """Return the token for the triple, or None when none is stored."""
        ...

    def put(self, user_id: str, agent_id: str, server_id: str, token: UserToken) -> None:
        """Store (insert or overwrite) the token for the triple."""
        ...

    def delete(self, user_id: str, agent_id: str, server_id: str) -> None:
        """Remove any token for the triple; a no-op when none exists."""
        ...


class InMemoryUserTokenStore:
    """In-process default :class:`UserTokenStore` for tests / no-persistence runs.

    Not a module-level global on its own — instances are created explicitly. The
    standalone fallback (:data:`_local_store`) is a single instance and is replaced,
    in production, by the SQLite-backed store wired at agent boot.
    """

    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str, str], UserToken] = {}

    def get(self, user_id: str, agent_id: str, server_id: str) -> UserToken | None:
        return self._tokens.get((user_id, agent_id, server_id))

    def put(self, user_id: str, agent_id: str, server_id: str, token: UserToken) -> None:
        self._tokens[(user_id, agent_id, server_id)] = token

    def delete(self, user_id: str, agent_id: str, server_id: str) -> None:
        self._tokens.pop((user_id, agent_id, server_id), None)


# Resolver seam (D5): signature ``(server_id, user_id, agent_id | None) -> UserToken | None``.
# managed startup injects a resolver that sources tokens through node→platform; standalone
# leaves it None and falls back to the local store. A callable reference only — no live
# resource is held at module scope.
UserTokenResolver = Callable[[str, str, str | None], "UserToken | None"]

_resolver: UserTokenResolver | None = None

# Standalone fallback store. Default is in-memory; agent boot replaces it with the
# SQLite-backed store via :func:`set_local_user_token_store`.
_local_store: UserTokenStore = InMemoryUserTokenStore()


def set_user_token_resolver(resolver: UserTokenResolver | None) -> None:
    """Wire (or clear) the injected per-user token resolver.

    The injected resolver belongs to managed startup code (slice 2) and may reach
    platform-owned token storage through the node; agent-runtime code must not depend
    on its implementation. Passing None reverts to the standalone local fallback.
    """
    global _resolver
    _resolver = resolver


def set_local_user_token_store(store: UserTokenStore) -> None:
    """Inject the standalone local token store used when no resolver is wired.

    Called once at agent boot to swap the default in-memory store for the SQLite-backed
    encrypted store. Independent of :func:`set_user_token_resolver`: when a resolver is
    injected it takes precedence and the local store is not consulted.
    """
    global _local_store
    _local_store = store


def resolve_user_token(
    server_id: str, user_id: str, agent_id: str | None = None
) -> UserToken | None:
    """Resolve the per-user token for a call, returning None when none exists.

    When a resolver is injected (managed) it is consulted; otherwise (standalone) the
    local store is queried by the full triple. A None result is the explicit "no token"
    signal that drives the authorization flow rather than an error.

    Args:
        server_id: The MCP server id the token authenticates against.
        user_id: The calling message sender's principal user id (per-message identity).
        agent_id: The agent id completing the isolation triple; required for the local
            store, optional in the resolver signature for managed flexibility.

    Returns:
        The :class:`UserToken` for the triple, or None when no token is stored.
    """
    if _resolver is not None:
        return _resolver(server_id, user_id, agent_id)
    return _local_store.get(user_id, agent_id or "", server_id)
