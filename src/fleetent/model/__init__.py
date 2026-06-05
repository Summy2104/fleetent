"""Model capability public API."""

from fleetent.model.provider_health import (
    ProviderHealthCache,
    ProviderState,
    get_health_cache,
)
from fleetent.model.resolver import (
    STANDARD_ROUTE_KEYS,
    ModelAuthError,
    ModelCallSwitchableError,
    ModelConfigError,
    ModelPolicySnapshot,
    ModelRouteEntrySnapshot,
    ModelTargetSnapshot,
    ResolvedModelConfig,
    call_with_policy,
)

__all__ = [
    "ProviderHealthCache",
    "ProviderState",
    "ModelAuthError",
    "ModelCallSwitchableError",
    "ModelConfigError",
    "ModelPolicySnapshot",
    "ModelRouteEntrySnapshot",
    "ModelTargetSnapshot",
    "ResolvedModelConfig",
    "STANDARD_ROUTE_KEYS",
    "call_with_policy",
    "get_health_cache",
]
