"""Admin block/unblock cascade orchestration.

Lives in the platform control plane because it coordinates platform-owned stores
(API keys, IM accounts). The agent-readable registration ban is delegated to
``governance.blocklist`` via its public API.
"""

import secrets

from fleetent import user_store
from fleetent import audit_log
from fleetent.governance import blocklist
from fleetent.platform import im_gateway_management as im
from fleetent.platform.user_management import api_key_store


def block_user(
    user_id: str, reason: str, actor: str | None = None, batch_id: str | None = None
) -> None:
    """Block a user and cascade: revoke keys, disable IM accounts, ban email re-registration."""
    user = user_store.get_by_id(user_id)
    if user is None:
        raise KeyError(f"user not found: {user_id}")
    if user.role == "built_in_admin":
        raise PermissionError("built-in admin cannot be blocked")

    user_store.set_status(user_id, "blocked")
    for key in api_key_store.list_keys(user_id):
        if key["revoked_at"] is None:
            api_key_store.revoke_key(key["id"])
    im.disable_im_accounts(user_id)
    if user.email:
        blocklist.ban_registration(user.email, reason, batch_id)
    audit_log.write_audit(
        actor,
        "block_user",
        target_type="user",
        target_id=user_id,
        detail={"reason": reason},
        batch_id=batch_id,
    )


def unblock_user(user_id: str, actor: str | None = None) -> None:
    """Restore login. Revoked keys are NOT revived; IM accounts need re-approval."""
    user_store.set_status(user_id, "active")
    audit_log.write_audit(actor, "unblock_user", target_type="user", target_id=user_id)


def batch_block(user_ids: list[str], reason: str, actor: str | None = None) -> str:
    """Block several users under one shared batch id. Returns the batch id."""
    batch_id = f"batch-{secrets.token_hex(6)}"
    for user_id in user_ids:
        block_user(user_id, reason=reason, actor=actor, batch_id=batch_id)
    return batch_id
