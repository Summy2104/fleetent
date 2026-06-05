"""IM identity mapping + per-identity allowlist (im_users table).

Part of the unified IM module. Maps (owner_id, platform, platform_user_id) to an
internal User and owns the approve/block/rebind admin workbench.
"""

import contextlib
import datetime
from typing import Any

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
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
    _init_db()
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
    user = create_user(name=f"{platform}:{platform_user_id}")
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
    _init_db()
    with _conn() as conn:
        row = conn.execute("SELECT allowed FROM im_users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return True
    return bool(row[0])


def approve_user(im_user_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 1 WHERE id = ?", (im_user_id,))


def block_user(im_user_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE id = ?", (im_user_id,))


def get_im_user(im_user_id: int) -> dict[str, Any] | None:
    """Fetch one IM identity by its im_users.id, or None if it does not exist."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, owner_id, platform, platform_user_id, user_id, allowed, created_at,"
            " meta_json FROM im_users WHERE id = ?",
            (im_user_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "owner_id": row[1],
        "platform": row[2],
        "platform_user_id": row[3],
        "user_id": row[4],
        "allowed": bool(row[5]),
        "created_at": row[6],
        "metadata": _parse_meta(row[7]),
    }


def disable_im_accounts(user_id: str) -> None:
    """Disallow every IM identity bound to an internal user (used by governance block)."""
    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE user_id = ?", (user_id,))


def block_im_user(
    im_user_id: int,
    reason: str | None = None,
    actor: str | None = None,
    batch_id: str | None = None,
) -> None:
    """Block a single IM identity (admin workbench). Audited."""
    from fleetent.governance import audit_log

    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 0 WHERE id = ?", (im_user_id,))
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
    from fleetent.governance import audit_log

    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE im_users SET allowed = 1 WHERE id = ?", (im_user_id,))
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
    from fleetent.governance import audit_log

    _init_db()
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

    from fleetent.governance import audit_log

    _init_db()
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
    from fleetent.governance import audit_log

    _init_db()
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
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, allowed, meta_json FROM im_users"
            " WHERE user_id = ? ORDER BY platform",
            (user_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "platform": r[1],
            "platform_user_id": r[2],
            "allowed": bool(r[3]),
            "metadata": _parse_meta(r[4]),
        }
        for r in rows
    ]


def list_all() -> list[dict[str, Any]]:
    """All IM identities across all users (for the admin workbench)."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, owner_id, platform, platform_user_id, user_id, allowed, created_at,"
            " meta_json FROM im_users ORDER BY created_at"
        ).fetchall()
    return [
        {
            "id": r[0],
            "owner_id": r[1],
            "platform": r[2],
            "platform_user_id": r[3],
            "user_id": r[4],
            "allowed": bool(r[5]),
            "created_at": r[6],
            "metadata": _parse_meta(r[7]),
        }
        for r in rows
    ]


def list_pending() -> list[dict[str, Any]]:
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, created_at"
            " FROM im_users WHERE allowed = 0 ORDER BY created_at"
        ).fetchall()
    return [
        {"id": r[0], "platform": r[1], "platform_user_id": r[2], "created_at": r[3]} for r in rows
    ]


def _init_db() -> None:
    from fleetent import user_store

    # Resolve the backfill owner before opening our own connection: admin_owner_id()
    # opens a separate connection on the same SQLite file, which would deadlock if a
    # write transaction were already held here.
    admin_owner = user_store.admin_owner_id()
    with _conn() as conn:
        # Migrate: add allowed column to pre-allowlist tables before any owner rebuild.
        try:
            conn.execute("ALTER TABLE im_users ADD COLUMN allowed BOOLEAN NOT NULL DEFAULT 0")
            # Existing users were already active before allowlist — grant access
            conn.execute("UPDATE im_users SET allowed = 1 WHERE allowed = 0")
        except Exception:
            pass  # Column already exists or table absent
        _rebuild_legacy_if_needed(conn, admin_owner)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_users (
                id               INTEGER PRIMARY KEY,
                owner_id         TEXT NOT NULL,
                platform         TEXT NOT NULL,
                platform_user_id TEXT NOT NULL,
                user_id          TEXT NOT NULL,
                allowed          BOOLEAN NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL,
                meta_json        TEXT,
                UNIQUE(owner_id, platform, platform_user_id)
            )"""
        )
        # Migrate: add the per-platform metadata blob to pre-048 tables (see migration 048).
        # Column may already exist (or table be absent) — both are fine.
        with contextlib.suppress(Exception):
            conn.execute("ALTER TABLE im_users ADD COLUMN meta_json TEXT")


def _rebuild_legacy_if_needed(conn: Any, owner: str) -> None:
    """Rebuild a pre-multi-tenant `im_users` (no owner_id) in place, backfilling owner_id
    with the built-in admin owner. Idempotent."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='im_users'"
    ).fetchone()
    if not exists:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(im_users)")}
    if "owner_id" in cols:
        return
    conn.execute("ALTER TABLE im_users RENAME TO im_users_legacy")
    conn.execute(
        """CREATE TABLE im_users (
            id               INTEGER PRIMARY KEY,
            owner_id         TEXT NOT NULL,
            platform         TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            user_id          TEXT NOT NULL,
            allowed          BOOLEAN NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL,
            UNIQUE(owner_id, platform, platform_user_id)
        )"""
    )
    conn.execute(
        """INSERT INTO im_users
               (id, owner_id, platform, platform_user_id, user_id, allowed, created_at)
           SELECT id, :owner, platform, platform_user_id, user_id, allowed, created_at
           FROM im_users_legacy""",
        {"owner": owner},
    )
    conn.execute("DROP TABLE im_users_legacy")
