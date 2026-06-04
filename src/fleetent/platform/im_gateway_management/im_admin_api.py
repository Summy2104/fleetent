"""Compatibility shim. Canonical home: …im_gateway_management.admin_api.

Re-export only — no business logic. Note: the start/stop seams are module-level
attributes on the canonical module; patch them there (server lifespan does).
"""

from fleetent.platform.im_gateway_management.admin_api import (  # noqa: F401
    router,
    start_connector,
    stop_connector,
)
