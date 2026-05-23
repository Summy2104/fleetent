import datetime

from mini_agent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from mini_agent.user_store import (
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
            " (platform, platform_user_id, user_id, created_at) VALUES (?, ?, ?, ?)",
            (platform, platform_user_id, user.id, now),
        )
    return user


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_users (
                id               INTEGER PRIMARY KEY,
                platform         TEXT NOT NULL,
                platform_user_id TEXT NOT NULL,
                user_id          TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                UNIQUE(platform, platform_user_id)
            )"""
        )
