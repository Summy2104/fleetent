"""Compatibility shim. Canonical home: …im_gateway_management.connector_store.

Re-export only — no business logic.
"""

from fleetent.platform.im_gateway_management.connector_store import (  # noqa: F401
    DB_PATH as DB_PATH,
)
from fleetent.platform.im_gateway_management.connector_store import (  # noqa: F401
    STATUSES,
    _init_db,
    get_connector,
    heartbeat,
    list_connectors,
    report_status,
    set_allowlist_enforced,
    set_enabled,
    upsert_connector,
)
