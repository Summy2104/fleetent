"""IM identity mapping + per-identity allowlist (im_users table).

Part of the unified IM module. Maps (owner_id, platform, platform_user_id) to an
internal User and owns the approve/block/rebind admin workbench.
"""

import datetime
from typing import Any

from fleetent.user_store import (
    User,
    _conn,
    create_user,
    get_by_id,
)

# Admin-editable, platform-specific identity attributes. The platform handle
# (platform + platform_user_id) is auto-captured by the gateway and is NOT here.
# Connection credentials (bot tokens etc.) are connector-scoped, not per-identity,
# so they never belong in this map. Add a field by appending here — the JSON
# meta_json column needs no migration.
PLATFORM_IDENTITY_FIELDS: dict[str, list[dict[str, Any]]] = {
    # Slack exposes a User ID (= platform_user_id, the read-only handle), plus a
    # Workspace ID and an Enterprise ID for org-grid workspaces.
    "slack": [
        {"key": "display_name", "label": "Display name"},
        {"key": "email", "label": "Email"},
        {"key": "team_id", "label": "Workspace ID"},
        {"key": "enterprise_id", "label": "Enterprise ID"},
        {"key": "notes", "label": "Notes", "multiline": True},
    ],
    "telegram": [
        {"key": "username", "label": "Username (@handle)"},
        {"key": "phone", "label": "Phone"},
        {"key": "notes", "label": "Notes", "multiline": True},
    ],
    "whatsapp": [
        {"key": "display_name", "label": "Display name"},
        {"key": "phone", "label": "Phone number"},
        {"key": "notes", "label": "Notes", "multiline": True},
    ],
}


def _parse_meta(raw: Any) -> dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_or_create(owner_id: str, platform: str, platform_user_id: str) -> User:
    with _conn() as conn:
        row = conn.execute(
            """SELECT user_id FROM im_users
               WHERE owner_id = :owner_id AND platform = :platform
                 AND platform_user_id = :puid""",
            {"owner_id": owner_id, "platform": platform, "puid": platform_user_id},
        ).fetchone()
    if row:
        user = get_by_id(row[0])
        assert user is not None
        return user

    with _conn() as conn:
        shared = conn.execute(
            """SELECT user_id FROM im_users
               WHERE platform = :platform AND platform_user_id = :puid
               ORDER BY id LIMIT 1""",
            {"platform": platform, "puid": platform_user_id},
        ).fetchone()

    if shared:
        user = get_by_id(shared[0])
        assert user is not None
    else:
        user, _ = create_user(name=f"{platform}:{platform_user_id}")

    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        # v1.0: new IM users are allowed by default; channel admission is handled by the
        # channel allowlist (see im-channel-allowlist), not per-user approval.
        conn.execute(
            """INSERT OR IGNORE INTO im_users
                   (owner_id, platform, platform_user_id, user_id, allowed, created_at)
               VALUES (:owner_id, :platform, :puid, :uid, 1, :now)""",
            {
                "owner_id": owner_id,
                "platform": platform,
                "puid": platform_user_id,
                "uid": user.id,
                "now": now,
            },
        )
    return user


def check_allowed_by_user_id(user_id: str) -> bool:
    """Return True if user is not in im_users (HTTP API user) or is explicitly allowed."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT allowed FROM im_users WHERE user_id = :user_id",
            {"user_id": user_id},
        ).fetchone()
    if row is None:
        return True
    return bool(row["allowed"])


def approve_user(im_user_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 1 WHERE id = :id", {"id": im_user_id})


def block_user(im_user_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE id = :id", {"id": im_user_id})


def get_im_user(im_user_id: int) -> dict[str, Any] | None:
    """Fetch one IM identity by its im_users.id, or None if it does not exist."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, owner_id, platform, platform_user_id, user_id, allowed, created_at,"
            " meta_json FROM im_users WHERE id = :id",
            {"id": im_user_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "platform": row["platform"],
        "platform_user_id": row["platform_user_id"],
        "user_id": row["user_id"],
        "allowed": bool(row["allowed"]),
        "created_at": row["created_at"],
        "metadata": _parse_meta(row["meta_json"]),
    }


def disable_im_accounts(user_id: str) -> None:
    """Disallow every IM identity bound to an internal user (used by governance block)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE im_users SET allowed = 0 WHERE user_id = :user_id", {"user_id": user_id}
        )


def block_im_user(
    im_user_id: int,
    reason: str | None = None,
    actor: str | None = None,
    batch_id: str | None = None,
) -> None:
    """Block a single IM identity (admin workbench). Audited."""
    from fleetent import audit_log

    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE id = :id", {"id": im_user_id})
    audit_log.write_audit(
        actor,
        "block_im_user",
        target_type="im_user",
        target_id=str(im_user_id),
        detail={"reason": reason},
        batch_id=batch_id,
    )


def restore_im_user(
    im_user_id: int,
    reason: str | None = None,
    actor: str | None = None,
    batch_id: str | None = None,
) -> None:
    """Restore a single IM identity (admin workbench). Audited."""
    from fleetent import audit_log

    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 1 WHERE id = :id", {"id": im_user_id})
    audit_log.write_audit(
        actor,
        "restore_im_user",
        target_type="im_user",
        target_id=str(im_user_id),
        detail={"reason": reason},
        batch_id=batch_id,
    )


def batch_block_im(im_user_ids: list[int], reason: str, actor: str | None = None) -> str:
    import secrets

    batch_id = f"batch-{secrets.token_hex(6)}"
    for im_user_id in im_user_ids:
        block_im_user(im_user_id, reason=reason, actor=actor, batch_id=batch_id)
    return batch_id


def rebind_im_identity(im_user_id: int, target_user_id: str, actor: str | None = None) -> None:
    """Point an IM identity at an existing internal user (many-to-one binding). Audited.

    The previously-bound user is left untouched (it may become an orphan with no IM identities).
    """
    from fleetent import audit_log

    if get_by_id(target_user_id) is None:
        raise ValueError(f"target user not found: {target_user_id}")
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE im_users SET user_id = :uid WHERE id = :id",
            {"uid": target_user_id, "id": im_user_id},
        )
        if cur.rowcount == 0:
            raise ValueError(f"im identity not found: {im_user_id}")
    audit_log.write_audit(
        actor,
        "rebind_im_user",
        target_type="im_user",
        target_id=str(im_user_id),
        detail={"user_id": target_user_id},
    )


def identity_fields(platform: str) -> list[dict[str, Any]]:
    """Admin-editable metadata fields for an IM identity on the given platform.

    The platform handle (platform, platform_user_id) is auto-captured by the gateway
    and never appears here. Unknown platforms have no editable fields.
    """
    return [dict(f) for f in PLATFORM_IDENTITY_FIELDS.get(platform, [])]


def update_im_identity(
    im_user_id: int,
    platform_user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    """Edit an IM identity. Audited.

    The platform User ID is auto-captured but admin-overridable: pass ``platform_user_id``
    to correct it (uniqueness-checked → ValueError "already exists" on collision). Pass
    ``metadata`` to replace the per-platform editable fields (keys outside the platform's
    schema are dropped). The platform, binding and allowlist are untouched. Raises
    ValueError if the identity does not exist.
    """
    import json
    import sqlite3

    from fleetent import audit_log

    detail: dict[str, Any] = {}
    with _conn() as conn:
        row = conn.execute(
            "SELECT platform FROM im_users WHERE id = :id", {"id": im_user_id}
        ).fetchone()
        if row is None:
            raise ValueError(f"im identity not found: {im_user_id}")
        if platform_user_id is not None:
            try:
                conn.execute(
                    "UPDATE im_users SET platform_user_id = :puid WHERE id = :id",
                    {"puid": platform_user_id, "id": im_user_id},
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"im identity already exists: {platform_user_id}") from exc
            detail["platform_user_id"] = platform_user_id
        if metadata is not None:
            allowed_keys = {f["key"] for f in PLATFORM_IDENTITY_FIELDS.get(row[0], [])}
            clean = {k: v for k, v in metadata.items() if k in allowed_keys}
            conn.execute(
                "UPDATE im_users SET meta_json = :m WHERE id = :id",
                {"m": json.dumps(clean), "id": im_user_id},
            )
            detail["metadata_keys"] = sorted(clean)
    audit_log.write_audit(
        actor,
        "update_im_user",
        target_type="im_user",
        target_id=str(im_user_id),
        detail=detail,
    )


def delete_im_identity(im_user_id: int, actor: str | None = None) -> None:
    """Delete an IM identity row. Audited. Raises ValueError if it does not exist.

    The previously-bound platform user is left untouched.
    """
    from fleetent import audit_log

    with _conn() as conn:
        cur = conn.execute("DELETE FROM im_users WHERE id = :id", {"id": im_user_id})
        if cur.rowcount == 0:
            raise ValueError(f"im identity not found: {im_user_id}")
    audit_log.write_audit(
        actor,
        "delete_im_user",
        target_type="im_user",
        target_id=str(im_user_id),
    )


def list_im_identities(user_id: str) -> list[dict[str, Any]]:
    """All IM identities (across platforms) belonging to one internal User."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, allowed, meta_json FROM im_users"
            " WHERE user_id = :user_id ORDER BY platform",
            {"user_id": user_id},
        ).fetchall()
    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "allowed": bool(r["allowed"]),
            "metadata": _parse_meta(r["meta_json"]),
        }
        for r in rows
    ]


def list_all() -> list[dict[str, Any]]:
    """All IM identities across all users (for the admin workbench)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, owner_id, platform, platform_user_id, user_id, allowed, created_at,"
            " meta_json FROM im_users ORDER BY created_at"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "owner_id": r["owner_id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "user_id": r["user_id"],
            "allowed": bool(r["allowed"]),
            "created_at": r["created_at"],
            "metadata": _parse_meta(r["meta_json"]),
        }
        for r in rows
    ]


def list_pending() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, created_at"
            " FROM im_users WHERE allowed = 0 ORDER BY created_at"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
