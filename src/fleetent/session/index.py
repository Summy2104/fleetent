"""Lightweight per-session metadata index stored in the unified agent DB.

Records creation/last-active time, message count, owning user and agent name for
each session. Physically separate from the session message files (manager);
written as a best-effort side effect after a successful message save.
"""

import os
import time

from fleetent import paths
from fleetent.db import SQLiteDatabase, create_database


def _database_url() -> str:
    default = f"sqlite:///{paths.data_dir() / 'fleetent.db'}"
    return os.environ.get("DATABASE_URL", default)


def _db() -> SQLiteDatabase:
    return create_database(_database_url())


def ensure_schema(db: SQLiteDatabase) -> None:
    """Create sessions table if it does not exist. Idempotent."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT,
            created_at    REAL,
            updated_at    REAL,
            message_count INTEGER,
            agent_name    TEXT
        )
        """
    )


def record_activity(
    session_id: str,
    user_id: str | None,
    message_count: int,
    agent_name: str | None,
) -> None:
    """Upsert metadata for a session.

    First write sets `created_at == updated_at == now`. A conflicting write keeps
    the original `created_at`, refreshes `updated_at`, and overwrites
    `message_count` / `user_id` / `agent_name`.
    """
    now = time.time()
    _db().execute(
        """
        INSERT INTO sessions
               (session_id, user_id, created_at, updated_at, message_count, agent_name)
        VALUES (:session_id, :user_id, :created_at, :updated_at, :message_count, :agent_name)
        ON CONFLICT(session_id) DO UPDATE SET
            user_id = excluded.user_id,
            updated_at = excluded.updated_at,
            message_count = excluded.message_count,
            agent_name = excluded.agent_name
        """,
        {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "message_count": message_count,
            "agent_name": agent_name,
        },
    )


_SELECT_COLS = "session_id, user_id, created_at, updated_at, message_count, agent_name"


def _row_to_dict(row: dict[str, object]) -> dict[str, object]:
    return {
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message_count": row["message_count"],
        "agent_name": row["agent_name"],
    }


def get(session_id: str) -> dict[str, object] | None:
    """Return a single session's metadata, or None when not recorded."""
    row = (
        _db()
        .execute(
            f"SELECT {_SELECT_COLS} FROM sessions WHERE session_id = :session_id",
            {"session_id": session_id},
        )
        .fetchone()
    )
    return _row_to_dict(row) if row else None


def list_by_user(
    user_id: str,
    limit: int = 50,
    before_updated_at: float | None = None,
) -> list[dict[str, object]]:
    """Return sessions for a user, most-recently-active first, with cursor pagination."""
    params: dict[str, object] = {"user_id": user_id, "limit": limit}
    cursor_clause = ""
    if before_updated_at is not None:
        cursor_clause = " AND updated_at < :before_updated_at"
        params["before_updated_at"] = before_updated_at
    rows = (
        _db()
        .execute(
            f"SELECT {_SELECT_COLS} FROM sessions"
            f" WHERE user_id = :user_id{cursor_clause} ORDER BY updated_at DESC LIMIT :limit",
            params,
        )
        .fetchall()
    )
    return [_row_to_dict(row) for row in rows]


def count() -> int:
    """Return the total number of recorded sessions."""
    row = _db().execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
    return int(row["n"]) if row else 0


def total_message_count() -> int:
    """Return the sum of `message_count` across all recorded sessions."""
    row = _db().execute("SELECT COALESCE(SUM(message_count), 0) AS s FROM sessions").fetchone()
    return int(row["s"]) if row else 0


def delete(session_id: str) -> None:
    """Remove a single session's metadata row. Idempotent: no-op if not present."""
    _db().execute("DELETE FROM sessions WHERE session_id = :session_id", {"session_id": session_id})


def delete_batch(session_ids: list[str]) -> None:
    """Remove metadata rows for multiple sessions in a single transaction."""
    if not session_ids:
        return
    db = _db()
    with db.transaction() as conn:
        for sid in session_ids:
            conn.execute("DELETE FROM sessions WHERE session_id = :session_id", {"session_id": sid})
