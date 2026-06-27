"""IM identity mapping + admin workbench over the im_users table.

Part of the unified IM module. Maps (platform, platform_user_id) to an internal
User and owns the admin workbench over that mapping.
"""

import datetime
import sqlite3
from typing import Any

from fleetent.user_store import (
    User,
    _conn,
    create_user,
    get_by_email,
    get_by_id,
    set_status,
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


def _get_mapped_user(platform: str, platform_user_id: str) -> User | None:
    with _conn() as conn:
        row = conn.execute(
            """SELECT user_id FROM im_users
               WHERE platform = :platform AND platform_user_id = :puid""",
            {"platform": platform, "puid": platform_user_id},
        ).fetchone()
    if row is None:
        return None
    user = get_by_id(row[0])
    assert user is not None
    return user


def get_mapped_user(platform: str, platform_user_id: str) -> User | None:
    return _get_mapped_user(platform, platform_user_id)


def _attach_identity(platform: str, platform_user_id: str, user_id: str) -> User:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO im_users
                   (platform, platform_user_id, user_id, created_at)
               VALUES (:platform, :puid, :uid, :now)""",
            {
                "platform": platform,
                "puid": platform_user_id,
                "uid": user_id,
                "now": now,
            },
        )
        if cursor.rowcount:
            created = get_by_id(user_id)
            assert created is not None
            return created
        row = conn.execute(
            """SELECT user_id FROM im_users
               WHERE platform = :platform AND platform_user_id = :puid""",
            {"platform": platform, "puid": platform_user_id},
        ).fetchone()
    assert row is not None
    existing = get_by_id(row[0])
    assert existing is not None
    return existing


def attach_identity(platform: str, platform_user_id: str, user_id: str) -> User:
    return _attach_identity(platform, platform_user_id, user_id)


def create_mapping(
    platform: str,
    platform_user_id: str,
    user_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Admin-create an IM identity mapping bound to an existing internal user. Audited.

    Unlike ``attach_identity`` (idempotent INSERT OR IGNORE used by the gateway), this is
    the admin-workbench primitive: it fails loudly so the API can surface conflicts.

    Raises ValueError "target user not found" if ``user_id`` has no user, or
    "im identity already exists" if ``(platform, platform_user_id)`` is already mapped.
    """
    from fleetent import audit_log

    user = get_by_id(user_id)
    if user is None:
        raise ValueError(f"target user not found: {user_id}")
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO im_users (platform, platform_user_id, user_id, created_at)
                   VALUES (:platform, :puid, :uid, :now)""",
                {"platform": platform, "puid": platform_user_id, "uid": user_id, "now": now},
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"im identity already exists: {platform}:{platform_user_id}") from exc
        new_id = cursor.lastrowid
    audit_log.write_audit(
        actor,
        "create_im_user",
        target_type="im_user",
        target_id=f"{platform}:{platform_user_id}",
        detail={
            "platform": platform,
            "platform_user_id": platform_user_id,
            "user_id": user_id,
        },
    )
    return {
        "id": new_id,
        "platform": platform,
        "platform_user_id": platform_user_id,
        "user_id": user_id,
        "user_name": user.name,
        "user_email": user.email,
        "created_at": now,
    }


def resolve_or_provision(
    tenant_id: str,
    *,
    verified_email: str | None = None,
    channel: str | None = None,
    platform_user_id: str | None = None,
) -> User:
    if channel is not None and platform_user_id is not None:
        mapped = _get_mapped_user(channel, platform_user_id)
        if mapped is not None:
            return mapped

    if verified_email is not None:
        existing = get_by_email(tenant_id, verified_email)
        if existing is not None:
            if channel is not None and platform_user_id is not None:
                return _attach_identity(channel, platform_user_id, existing.id)
            return existing
        try:
            created, _ = create_user(
                name=verified_email.strip(), email=verified_email, tenant_id=tenant_id
            )
        except sqlite3.IntegrityError:
            created = get_by_email(tenant_id, verified_email)
            assert created is not None
        if channel is not None and platform_user_id is not None:
            return _attach_identity(channel, platform_user_id, created.id)
        return created

    if channel is None or platform_user_id is None:
        raise ValueError("channel and platform_user_id are required when verified_email is absent")

    created, _ = create_user(name=f"{channel}:{platform_user_id}", tenant_id=tenant_id)
    return _attach_identity(channel, platform_user_id, created.id)


def get_or_create(
    platform: str,
    platform_user_id: str,
    edge_tenant: str,
    *,
    verified_email: str | None = None,
) -> User:
    return resolve_or_provision(
        edge_tenant,
        verified_email=verified_email,
        channel=platform,
        platform_user_id=platform_user_id,
    )


def check_allowed_by_user_id(user_id: str) -> bool:
    """Compatibility shim over the canonical users.status block state."""
    user = get_by_id(user_id)
    return user is None or user.status != "blocked"


def approve_user(im_user_id: int) -> None:
    restore_im_user(im_user_id)


def block_user(im_user_id: int) -> None:
    block_im_user(im_user_id)


def get_im_user(im_user_id: int) -> dict[str, Any] | None:
    """Fetch one IM identity by its im_users.id, or None if it does not exist."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT im.id, im.platform, im.platform_user_id, im.user_id, im.created_at,"
            " im.meta_json, users.status"
            " FROM im_users AS im JOIN users ON users.id = im.user_id"
            " WHERE im.id = :id",
            {"id": im_user_id},
        ).fetchone()
    if row is None:
        return None
    allowed = row["status"] != "blocked"
    return {
        "id": row["id"],
        "platform": row["platform"],
        "platform_user_id": row["platform_user_id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "allowed": allowed,
        "created_at": row["created_at"],
        "metadata": _parse_meta(row["meta_json"]),
    }


def disable_im_accounts(user_id: str) -> None:
    """No-op compatibility shim; IM blocking is enforced via users.status."""
    return None


def block_im_user(
    im_user_id: int,
    reason: str | None = None,
    actor: str | None = None,
    batch_id: str | None = None,
) -> None:
    """Block a single IM identity (admin workbench). Audited."""
    from fleetent import audit_log

    row = get_im_user(im_user_id)
    if row is None:
        raise ValueError(f"im identity not found: {im_user_id}")
    set_status(row["user_id"], "blocked")
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

    row = get_im_user(im_user_id)
    if row is None:
        raise ValueError(f"im identity not found: {im_user_id}")
    set_status(row["user_id"], "active")
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


def resolve_user_addresses(user_id: str) -> list[dict[str, str]]:
    """Return all IM bindings for a user as a list of {platform, platform_user_id} dicts.

    Used by the node reverse-lookup endpoint to fan-out delivery to all of the user's
    connected channels. Returns an empty list when the user has no bindings.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT platform, platform_user_id FROM im_users WHERE user_id = :uid",
            {"uid": user_id},
        ).fetchall()
    return [
        {"platform": str(r["platform"]), "platform_user_id": str(r["platform_user_id"])}
        for r in rows
    ]


def unlink_identity(platform: str, platform_user_id: str) -> None:
    """Delete one platform identity mapping if it exists."""
    with _conn() as conn:
        conn.execute(
            """DELETE FROM im_users
               WHERE platform = :platform AND platform_user_id = :puid""",
            {"platform": platform, "puid": platform_user_id},
        )


def list_im_identities(user_id: str) -> list[dict[str, Any]]:
    """All IM identities (across platforms) belonging to one internal User."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT im.id, im.platform, im.platform_user_id, im.meta_json, users.status"
            " FROM im_users AS im JOIN users ON users.id = im.user_id"
            " WHERE im.user_id = :user_id ORDER BY im.platform",
            {"user_id": user_id},
        ).fetchall()
    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "status": r["status"],
            "allowed": r["status"] != "blocked",
            "metadata": _parse_meta(r["meta_json"]),
        }
        for r in rows
    ]


def list_all() -> list[dict[str, Any]]:
    """All IM identities across all users (for the admin workbench).

    Each row carries the bound internal user's name and email alongside the opaque
    user_id so the IM-users page can show who an external identity maps to, while
    keeping the block-state fields (status/allowed/metadata) the page relies on.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT im.id, im.platform, im.platform_user_id, im.user_id, im.created_at,"
            " im.meta_json, users.status, users.name AS user_name, users.email AS user_email"
            " FROM im_users AS im JOIN users ON users.id = im.user_id"
            " ORDER BY im.created_at"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "user_email": r["user_email"],
            "status": r["status"],
            "allowed": r["status"] != "blocked",
            "created_at": r["created_at"],
            "metadata": _parse_meta(r["meta_json"]),
        }
        for r in rows
    ]


def list_mappings() -> list[dict[str, Any]]:
    """All IM identity mappings joined with the bound internal user's name and email.

    For the admin user↔IM relationship workbench: each row carries the platform handle
    plus the internal user it resolves to (name + email), so the page can show who an
    external identity maps to without a second lookup.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT im.id, im.platform, im.platform_user_id, im.user_id, im.created_at,"
            " users.name AS user_name, users.email AS user_email"
            " FROM im_users AS im JOIN users ON users.id = im.user_id"
            " ORDER BY im.created_at, im.id"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "platform_user_id": r["platform_user_id"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "user_email": r["user_email"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def list_pending() -> list[dict[str, Any]]:
    return []
