"""Lightweight per-session metadata index stored in users.db.

Records creation/last-active time, message count, owning user and agent name for
each session. Physically separate from the session message files (manager);
written as a best-effort side effect after a successful message save.
"""

import sqlite3
import time

from fleetent import paths

DB_PATH = paths.data_dir() / "users.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                session_id    TEXT PRIMARY KEY,
                user_id       TEXT,
                created_at    REAL,
                updated_at    REAL,
                message_count INTEGER,
                agent_name    TEXT
            )"""
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
    _init_db()
    now = time.time()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO sessions
                   (session_id, user_id, created_at, updated_at, message_count, agent_name)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   user_id = excluded.user_id,
                   updated_at = excluded.updated_at,
                   message_count = excluded.message_count,
                   agent_name = excluded.agent_name""",
            (session_id, user_id, now, now, message_count, agent_name),
        )


_SELECT_COLS = "session_id, user_id, created_at, updated_at, message_count, agent_name"


def _row_to_dict(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "session_id": row[0],
        "user_id": row[1],
        "created_at": row[2],
        "updated_at": row[3],
        "message_count": row[4],
        "agent_name": row[5],
    }


def get(session_id: str) -> dict[str, object] | None:
    """Return a single session's metadata, or None when not recorded."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLS} FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_by_user(user_id: str) -> list[dict[str, object]]:
    """Return all sessions for a user, most-recently-active first."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count() -> int:
    """Return the total number of recorded sessions."""
    _init_db()
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
    return int(row[0])


def total_message_count() -> int:
    """Return the sum of `message_count` across all recorded sessions."""
    _init_db()
    with _conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(message_count), 0) FROM sessions").fetchone()
    return int(row[0])
