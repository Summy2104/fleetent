"""Compatibility shim. Canonical home: fleetent.platform.im_gateway_management.identity.

Re-export only — no business logic. Remove once first-party imports use the canonical
path (see change merge-im-connectors-into-im-users, cleanup follow-up).
"""

from fleetent.platform.im_gateway_management.identity import (  # noqa: F401
    approve_user,
    batch_block_im,
    block_im_user,
    block_user,
    check_allowed_by_user_id,
    get_or_create,
    list_all,
    list_im_identities,
    list_pending,
    rebind_im_identity,
    restore_im_user,
)
