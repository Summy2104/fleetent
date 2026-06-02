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


def get_or_create(platform: str, platform_user_id: str) -> User:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT user_id FROM im_users WHERE platform = ? AND platform_user_id = ?",
            (platform, platform_user_id),
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
            "INSERT OR IGNORE INTO im_users"
            " (platform, platform_user_id, user_id, allowed, created_at) VALUES (?, ?, ?, 1, ?)",
            (platform, platform_user_id, user.id, now),
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


def block_im_user(
    im_user_id: int,
    reason: str | None = None,
    actor: str | None = None,
    batch_id: str | None = None,
) -> None:
    """Block a single IM identity (admin workbench). Audited."""
    from fleetent import audit_log

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
    from fleetent import audit_log

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


def list_im_identities(user_id: str) -> list[dict[str, Any]]:
    """All IM identities (across platforms) belonging to one internal User."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, allowed FROM im_users WHERE user_id = ?"
            " ORDER BY platform",
            (user_id,),
        ).fetchall()
    return [
        {"id": r[0], "platform": r[1], "platform_user_id": r[2], "allowed": bool(r[3])}
        for r in rows
    ]


def list_all() -> list[dict[str, Any]]:
    """All IM identities across all users (for the admin workbench)."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, user_id, allowed, created_at"
            " FROM im_users ORDER BY created_at"
        ).fetchall()
    return [
        {
            "id": r[0], "platform": r[1], "platform_user_id": r[2],
            "user_id": r[3], "allowed": bool(r[4]), "created_at": r[5],
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
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_users (
                id               INTEGER PRIMARY KEY,
                platform         TEXT NOT NULL,
                platform_user_id TEXT NOT NULL,
                user_id          TEXT NOT NULL,
                allowed          BOOLEAN NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL,
                UNIQUE(platform, platform_user_id)
            )"""
        )
        # Migrate: add allowed column to existing tables
        try:
            conn.execute("ALTER TABLE im_users ADD COLUMN allowed BOOLEAN NOT NULL DEFAULT 0")
            # Existing users were already active before allowlist — grant access
            conn.execute("UPDATE im_users SET allowed = 1 WHERE allowed = 0")
        except Exception:
            pass  # Column already exists
