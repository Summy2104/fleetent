"""Base Identity port: Principal contract + IdentityPort protocol + agent-side adapters.

The agent core and edge entry-points depend only on these types; authn
implementations live in adapters and are never imported by the runtime.

This module MUST NOT import fleetent.platform.* — it is part of the agent runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class Principal:
    """Minimal authenticated identity consumed by the agent core.

    Intentionally lean: role, scopes, display_name, and team stay outside the
    core contract (edge / governance concern).
    """

    user_id: str
    tenant_id: str


INGRESS_PRINCIPAL_HEADER = "X-Fleetent-Principal"


def encode_ingress_principal(principal: Principal) -> str:
    """Encode a trusted ingress Principal into a compact transport header string."""
    return json.dumps(
        {"user_id": principal.user_id, "tenant_id": principal.tenant_id},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def decode_ingress_principal(value: str | None) -> Principal | None:
    """Decode a trusted ingress Principal header value.

    Missing headers return None; malformed values raise ValueError so callers can reject
    bad trusted-transport requests instead of silently changing identity semantics.
    """
    if value is None or not value.strip():
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("principal header must decode to an object")
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("principal header missing user_id")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("principal header missing tenant_id")
    return Principal(user_id=user_id, tenant_id=tenant_id)


class IdentityPort(Protocol):
    """Resolve credentials to a Principal or reject (return None)."""

    def __call__(self, credentials: str) -> Principal | None: ...


# Canonical system-level principal for infrastructure tasks with no human owner.
SYSTEM_PRINCIPAL = Principal(user_id="system", tenant_id="system")


class LocalBearerAdapter:
    """Resolve a bearer token via the local api_keys table (SHA-256 hash comparison).

    Suitable for standalone agents; delegates to user_store.authenticate which queries
    api_keys directly without importing fleetent.platform.*.
    """

    def __call__(self, credentials: str) -> Principal | None:
        from fleetent.user_store import authenticate  # noqa: PLC0415

        result = authenticate(credentials)
        if result is None:
            return None
        user, _ = result
        return Principal(user_id=user.id, tenant_id=user.tenant_id)
