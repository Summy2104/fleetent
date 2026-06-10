"""Platform-side bearer adapter: resolves api_keys table entries to Principal.

This adapter is injected into the platform server at startup. It is the only
code that queries the api_keys table; the agent runtime never imports this module.
"""

from __future__ import annotations

from typing import Any

from fleetent.identity import Principal
from fleetent.platform.user_management import api_key_store
from fleetent.user_store import get_by_id


class PlatformBearerAdapter:
    """Resolve a bearer token via the platform api_keys table, returning a Principal.

    Falls back to None when the key is unknown, revoked, expired, or its owning
    user is blocked. Standalone agents never instantiate this class.
    """

    def __call__(self, credentials: str) -> Principal | None:
        meta: dict[str, Any] | None = api_key_store.resolve(credentials)
        if meta is None:
            return None
        user = get_by_id(meta["user_id"])
        if user is None or user.status == "blocked":
            return None
        return Principal(user_id=user.id, tenant_id=user.tenant_id)
