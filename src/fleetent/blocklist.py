"""User block/unblock with cascade (revoke keys, disable IM, ban re-registration) + audit."""

import datetime
import secrets

from fleetent import api_key_store, audit_log, im_user_store, user_store
from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)


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
    _disable_im_accounts(user_id)
    if user.email:
        _ban_registration(user.email, reason, batch_id)
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


def is_registration_blocked(email: str) -> bool:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM blocked_registrations WHERE email = ?", (email,)
        ).fetchone()
    return row is not None


def _disable_im_accounts(user_id: str) -> None:
    im_user_store._init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE user_id = ?", (user_id,))


def _ban_registration(email: str, reason: str, batch_id: str | None) -> None:
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO blocked_registrations (email, reason, batch_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (email, reason, batch_id, now),
        )


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS blocked_registrations (
                email      TEXT PRIMARY KEY,
                reason     TEXT,
                batch_id   TEXT,
                created_at TEXT NOT NULL
            )"""
        )
