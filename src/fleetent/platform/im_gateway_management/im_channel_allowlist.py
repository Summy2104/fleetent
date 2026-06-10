"""Compatibility shim. Canonical home: …im_gateway_management.channel_allowlist.

Re-export only — no business logic.
"""

from fleetent.platform.im_gateway_management.channel_allowlist import (  # noqa: F401
    DB_PATH as DB_PATH,
)
from fleetent.platform.im_gateway_management.channel_allowlist import (  # noqa: F401
    add_entry,
    is_allowed,
    list_entries,
    remove_entry,
)
