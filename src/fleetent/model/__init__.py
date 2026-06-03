"""Model capability public API.

Route task types to OpenAI-compatible endpoints (`router`) and track provider
circuit-breaker health (`provider_health`). Cross-package callers import the
public symbols from here, not from the internal modules.

Mutable module globals — ``ROUTES`` and ``ROUTES_PATH`` (router) — are
re-exported below as *reference copies*. Reassigning them on this package has
no effect on the live module. Callers and tests that need to mutate them MUST
operate on the ``fleetent.model.router`` module attributes directly (e.g.
``monkeypatch.setattr(fleetent.model.router, "ROUTES_PATH", ...)``), not on this
package namespace.
"""

from fleetent.model.provider_health import (
    ProviderHealthCache,
    ProviderState,
    get_health_cache,
)
from fleetent.model.router import (
    ROUTES,
    ROUTES_PATH,
    RouteConfig,
    RouteOverride,
    get_async_client_and_config,
    get_client_and_config,
)

__all__ = [
    "ROUTES",
    "ROUTES_PATH",
    "ProviderHealthCache",
    "ProviderState",
    "RouteConfig",
    "RouteOverride",
    "get_async_client_and_config",
    "get_client_and_config",
    "get_health_cache",
]
