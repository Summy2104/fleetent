"""Base Identity port: Principal contract + IdentityPort protocol + agent-side adapters.

The agent core and edge entry-points depend only on these types; authn
implementations live in adapters and are never imported by the runtime.

This module MUST NOT import fleetent.platform.* — it is part of the agent runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fleetent.user_store import User


@dataclass(frozen=True)
class Principal:
    """Minimal authenticated identity consumed by the agent core.

    Intentionally lean: role, scopes, display_name, and team stay outside the
    core contract (edge / governance concern).
    """

    user_id: str
    tenant_id: str


class IdentityPort(Protocol):
    """Resolve credentials to a Principal or reject (return None)."""

    def __call__(self, credentials: str) -> Principal | None: ...


# Canonical system-level principal for infrastructure tasks with no human owner.
SYSTEM_PRINCIPAL = Principal(user_id="system", tenant_id="system")


def _legacy_key_lookup(plaintext: str) -> "User | None":
    """Look up a user by legacy users.api_key column — no platform import."""
    from fleetent.user_store import _get_by_legacy_key  # noqa: PLC0415

    return _get_by_legacy_key(plaintext)


class LocalBearerAdapter:
    """Resolve a bearer token using only the local users.api_key column.

    Suitable for standalone agents that have no access to platform tables.
    Never imports fleetent.platform.*.
    """

    def __call__(self, credentials: str) -> Principal | None:
        user = _legacy_key_lookup(credentials)
        if user is None or user.status == "blocked":
            return None
        return Principal(user_id=user.id, tenant_id=user.tenant_id)
