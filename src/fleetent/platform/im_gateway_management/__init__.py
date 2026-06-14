"""Unified IM module: identity mapping and IM-user administration only."""

from fleetent.platform.im_gateway_management.identity import (
    PLATFORM_IDENTITY_FIELDS,
    approve_user,
    block_im_user,
    check_allowed_by_user_id,
    delete_im_identity,
    disable_im_accounts,
    get_im_user,
    get_or_create,
    identity_fields,
    list_all,
    list_im_identities,
    list_pending,
    rebind_im_identity,
    restore_im_user,
    update_im_identity,
)

__all__ = [
    "PLATFORM_IDENTITY_FIELDS",
    "approve_user",
    "block_im_user",
    "check_allowed_by_user_id",
    "delete_im_identity",
    "disable_im_accounts",
    "get_im_user",
    "get_or_create",
    "identity_fields",
    "list_all",
    "list_im_identities",
    "list_pending",
    "rebind_im_identity",
    "update_im_identity",
    "restore_im_user",
]
