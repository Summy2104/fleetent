"""Compatibility shim. Canonical home: …im_gateway_management.connector_config.

Re-export only — no business logic.
"""

from fleetent.platform.im_gateway_management.connector_config import (  # noqa: F401
    PLATFORM_CONFIG_KEYS,
    get_settings,
    resolve,
    resolve_masked,
    seed_from_env,
    set_config,
)
