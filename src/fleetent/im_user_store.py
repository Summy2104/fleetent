import datetime

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
        conn.execute(
            "INSERT OR IGNORE INTO im_users"
            " (platform, platform_user_id, user_id, allowed, created_at) VALUES (?, ?, ?, 0, ?)",
            (platform, platform_user_id, user.id, now),
        )
    return user


def check_allowed_by_user_id(user_id: str) -> bool:
    """Return True if user is not in im_users (HTTP API user) or is explicitly allowed."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT allowed FROM im_users WHERE user_id = ?", (user_id,)
        ).fetchone()
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


def list_pending() -> list[dict]:
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, platform_user_id, created_at"
            " FROM im_users WHERE allowed = 0 ORDER BY created_at"
        ).fetchall()
    return [
        {"id": r[0], "platform": r[1], "platform_user_id": r[2], "created_at": r[3]}
        for r in rows
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
            conn.execute(
                "ALTER TABLE im_users ADD COLUMN allowed BOOLEAN NOT NULL DEFAULT 0"
            )
            # Existing users were already active before allowlist — grant access
            conn.execute("UPDATE im_users SET allowed = 1 WHERE allowed = 0")
        except Exception:
            pass  # Column already exists
