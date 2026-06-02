"""Compatibility shim for governance blocklist."""

from fleetent.governance.blocklist import (
    DB_PATH,
    _ban_registration,
    _disable_im_accounts,
    _init_db,
    batch_block,
    block_user,
    is_registration_blocked,
    unblock_user,
)

__all__ = [
    "DB_PATH",
    "batch_block",
    "block_user",
    "is_registration_blocked",
    "unblock_user",
    "_disable_im_accounts",
    "_ban_registration",
    "_init_db",
]
