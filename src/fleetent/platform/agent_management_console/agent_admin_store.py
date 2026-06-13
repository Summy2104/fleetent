"""Management state for the Agent console: lifecycle status + provenance + drift."""

import datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_STATUSES = {"enabled", "disabled", "archived"}


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def get_state(agent_id: int) -> dict[str, Any]:
    row = (
        _database()
        .execute(
            """
            SELECT
                agent_admin_state.agent_id,
                agents.name AS agent_name,
                agent_admin_state.status,
                agent_admin_state.provenance,
                agent_admin_state.drift,
                agent_admin_state.archived_at,
                agent_admin_state.updated_at
            FROM agent_admin_state
            LEFT JOIN agents ON agents.id = agent_admin_state.agent_id
            WHERE agent_admin_state.agent_id = :agent_id
            """,
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    if row is None:
        return {
            "agent_id": agent_id,
            "agent_name": _agent_name(agent_id),
            "status": "enabled",
            "provenance": "adhoc",
            "drift": 0,
            "archived_at": None,
            "updated_at": None,
        }
    return row


def set_status(agent_id: int, status: str) -> None:
    if status not in _STATUSES:
        raise ValueError(f"unknown status: {status}")
    archived_at = _now() if status == "archived" else None
    _upsert(agent_id, {"status": status, "archived_at": archived_at})


def enable(agent_id: int) -> None:
    set_status(agent_id, "enabled")


def disable(agent_id: int) -> None:
    set_status(agent_id, "disabled")


def archive(agent_id: int) -> None:
    set_status(agent_id, "archived")


def restore(agent_id: int) -> None:
    set_status(agent_id, "enabled")


def set_provenance(agent_id: int, provenance: str) -> None:
    if provenance not in {"managed", "adhoc"}:
        raise ValueError(f"unknown provenance: {provenance}")
    _upsert(agent_id, {"provenance": provenance})


def mark_drift(agent_id: int) -> None:
    """Flag a managed agent as drifted (UI edited it out-of-band); adhoc is a no-op."""
    if get_state(agent_id)["provenance"] == "managed":
        _upsert(agent_id, {"drift": 1})


def clear_drift(agent_id: int) -> None:
    _upsert(agent_id, {"drift": 0})


def list_states(include_archived: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT
            agent_admin_state.agent_id,
            agents.name AS agent_name,
            agent_admin_state.status,
            agent_admin_state.provenance,
            agent_admin_state.drift,
            agent_admin_state.archived_at,
            agent_admin_state.updated_at
        FROM agent_admin_state
        LEFT JOIN agents ON agents.id = agent_admin_state.agent_id
        """
    if not include_archived:
        sql += " WHERE status != 'archived'"
    return _database().execute(sql + " ORDER BY agents.name, agent_admin_state.agent_id").fetchall()


def references(agent_id: int) -> dict[str, Any]:
    """Who references an agent — drives archive protection."""
    db = _database()
    users = [
        r["user_id"]
        for r in db.execute(
            "SELECT user_id FROM user_agents WHERE agent_id = :aid ORDER BY user_id",
            {"aid": agent_id},
        ).fetchall()
    ]
    channels = [
        f"{r['platform']}:{r['channel_id']}"
        for r in db.execute(
            "SELECT platform, channel_id FROM channel_agents WHERE agent_id = :aid "
            "ORDER BY platform, channel_id",
            {"aid": agent_id},
        ).fetchall()
    ]
    return {"users": users, "channels": channels}


def is_referenced(agent_id: int) -> bool:
    refs = references(agent_id)
    return bool(refs["users"] or refs["channels"])


def delete_state(agent_id: int) -> None:
    """Remove the side-table row for a hard-deleted agent; missing is a no-op."""
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM agent_admin_state WHERE agent_id = :agent_id", {"agent_id": agent_id}
        )


_FIELDS = {"status", "provenance", "drift", "archived_at"}
_DEFAULTS = {"status": "enabled", "provenance": "adhoc", "drift": 0, "archived_at": None}


def _agent_name(agent_id: int) -> str | None:
    row = (
        _database()
        .execute("SELECT name FROM agents WHERE id = :agent_id", {"agent_id": agent_id})
        .fetchone()
    )
    return None if row is None else str(row["name"])


def _upsert(agent_id: int, fields: dict[str, Any]) -> None:
    merged = {**_DEFAULTS, **{k: v for k, v in fields.items() if k in _FIELDS}}
    assignments = ", ".join(f"{k} = :{k}" for k in fields if k in _FIELDS)
    params = {**merged, "agent_id": agent_id, "updated_at": _now()}
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_admin_state
                (agent_id, status, provenance, drift, archived_at, updated_at)
            VALUES (:agent_id, :status, :provenance, :drift, :archived_at, :updated_at)
            ON CONFLICT(agent_id) DO UPDATE SET {assignments}, updated_at = :updated_at
            """.replace("{assignments}", assignments),
            params,
        )
