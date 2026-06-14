"""Management metadata for chat sessions (origin / status / takeover / pinned)."""

import datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_COLS = (
    "session_meta.session_id, session_meta.origin, session_meta.status, "
    "session_meta.takeover_actor, session_meta.takeover_at, session_meta.pinned, "
    "session_meta.pin_note, session_meta.agent_id, agents.name AS agent_name, "
    "session_meta.user_id, session_meta.channel, session_meta.updated_at"
)


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def upsert_meta(
    session_id: str,
    origin: str = "web",
    agent_id: int | None = None,
    user_id: str | None = None,
    channel: str | None = None,
) -> None:
    """Create/refresh the descriptive metadata for a session (idempotent)."""
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO session_meta
                (session_id, origin, status, pinned, agent_id, user_id, channel, updated_at)
            VALUES (:session_id, :origin, 'active', 0, :agent_id, :user_id, :channel, :updated_at)
            ON CONFLICT(session_id) DO UPDATE SET
                agent_id = excluded.agent_id,
                user_id = excluded.user_id,
                channel = excluded.channel,
                updated_at = excluded.updated_at
            """,
            {
                "session_id": session_id,
                "origin": origin,
                "agent_id": agent_id,
                "user_id": user_id,
                "channel": channel,
                "updated_at": _now(),
            },
        )


def get_meta(session_id: str) -> dict[str, Any]:
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM session_meta "
            "LEFT JOIN agents ON agents.id = session_meta.agent_id "
            "WHERE session_meta.session_id = :sid",
            {"sid": session_id},
        )
        .fetchone()
    )
    if row is None:
        return {
            "session_id": session_id,
            "origin": "web",
            "status": "active",
            "takeover_actor": None,
            "takeover_at": None,
            "pinned": 0,
            "pin_note": None,
            "agent_id": None,
            "agent_name": None,
            "user_id": None,
            "channel": None,
            "updated_at": None,
        }
    return row


def set_status(session_id: str, status: str) -> None:
    if status not in {"active", "idle", "ended"}:
        raise ValueError(f"unknown status: {status}")
    _update(session_id, {"status": status})


def set_takeover(session_id: str, actor: str) -> None:
    _update(session_id, {"takeover_actor": actor, "takeover_at": _now()})


def clear_takeover(session_id: str) -> None:
    _update(session_id, {"takeover_actor": None, "takeover_at": None})


def set_pinned(session_id: str, pinned: bool, note: str | None = None) -> None:
    _update(session_id, {"pinned": 1 if pinned else 0, "pin_note": note})


def is_taken_over(session_id: str) -> bool:
    return get_meta(session_id)["takeover_actor"] is not None


def list_meta(
    *,
    include_playground: bool = False,
    status: str | None = None,
    user_id: str | None = None,
    agent_id: int | None = None,
) -> list[dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if not include_playground:
        clauses.append("origin != 'playground'")
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if user_id:
        clauses.append("user_id = :user_id")
        params["user_id"] = user_id
    if agent_id is not None:
        clauses.append("session_meta.agent_id = :agent_id")
        params["agent_id"] = agent_id
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return (
        _database()
        .execute(
            f"SELECT {_COLS} FROM session_meta "
            "LEFT JOIN agents ON agents.id = session_meta.agent_id"
            f"{where} ORDER BY session_meta.updated_at DESC",
            params,
        )
        .fetchall()
    )


def list_unpinned_playground(before: str) -> list[str]:
    """Playground sessions not pinned and older than ``before`` — retention cleanup."""
    rows = (
        _database()
        .execute(
            "SELECT session_id FROM session_meta "
            "WHERE origin = 'playground' AND pinned = 0 AND updated_at < :before",
            {"before": before},
        )
        .fetchall()
    )
    return [r["session_id"] for r in rows]


def delete_meta(session_id: str) -> None:
    """Drop a session's governance metadata (retention cleanup)."""
    with _database().transaction() as conn:
        conn.execute("DELETE FROM session_meta WHERE session_id = :sid", {"sid": session_id})


_UPDATABLE = {"status", "takeover_actor", "takeover_at", "pinned", "pin_note"}


def _update(session_id: str, fields: dict[str, Any]) -> None:
    safe = {k: v for k, v in fields.items() if k in _UPDATABLE}
    safe["updated_at"] = _now()
    assignments = ", ".join(f"{k} = :{k}" for k in safe)
    with _database().transaction() as conn:
        # ensure a row exists, then update (origin defaults to web for unseen ids)
        conn.execute(
            "INSERT INTO session_meta (session_id, origin, status, pinned, updated_at) "
            "VALUES (:sid, 'web', 'active', 0, :now) ON CONFLICT(session_id) DO NOTHING",
            {"sid": session_id, "now": _now()},
        )
        conn.execute(
            f"UPDATE session_meta SET {assignments} WHERE session_id = :sid",
            {**safe, "sid": session_id},
        )
