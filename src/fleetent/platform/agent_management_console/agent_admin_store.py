"""Management state for the Agent console: lifecycle status + provenance + drift.

db runtime + named params, no ORM. Kept in a side table (agent_admin_state) keyed by
agent name so it does not depend on the agents main-table schema. Reference protection
queries the existing user_agents / channel_agents binding tables.

Identity is the agent name/id: flipping provenance (managed/adhoc) or status never
rebuilds the agent, so history and bindings carry over.
"""

import datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_STATUSES = {"enabled", "disabled", "archived"}


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def get_state(agent_name: str) -> dict[str, Any]:
    row = (
        _database()
        .execute(
            "SELECT agent_name, status, provenance, drift, archived_at, updated_at "
            "FROM agent_admin_state WHERE agent_name = :name",
            {"name": agent_name},
        )
        .fetchone()
    )
    if row is None:
        return {
            "agent_name": agent_name,
            "status": "enabled",
            "provenance": "adhoc",
            "drift": 0,
            "archived_at": None,
            "updated_at": None,
        }
    return row


def set_status(agent_name: str, status: str) -> None:
    if status not in _STATUSES:
        raise ValueError(f"unknown status: {status}")
    archived_at = _now() if status == "archived" else None
    _upsert(agent_name, {"status": status, "archived_at": archived_at})


def enable(agent_name: str) -> None:
    set_status(agent_name, "enabled")


def disable(agent_name: str) -> None:
    set_status(agent_name, "disabled")


def archive(agent_name: str) -> None:
    set_status(agent_name, "archived")


def restore(agent_name: str) -> None:
    set_status(agent_name, "enabled")


def set_provenance(agent_name: str, provenance: str) -> None:
    if provenance not in {"managed", "adhoc"}:
        raise ValueError(f"unknown provenance: {provenance}")
    _upsert(agent_name, {"provenance": provenance})


def mark_drift(agent_name: str) -> None:
    """Flag a managed agent as drifted (UI edited it out-of-band); adhoc is a no-op."""
    if get_state(agent_name)["provenance"] == "managed":
        _upsert(agent_name, {"drift": 1})


def clear_drift(agent_name: str) -> None:
    _upsert(agent_name, {"drift": 0})


def list_states(include_archived: bool = False) -> list[dict[str, Any]]:
    sql = (
        "SELECT agent_name, status, provenance, drift, archived_at, updated_at "
        "FROM agent_admin_state"
    )
    if not include_archived:
        sql += " WHERE status != 'archived'"
    return _database().execute(sql + " ORDER BY agent_name").fetchall()


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


def delete_state(agent_name: str) -> None:
    """Remove the side-table row for a hard-deleted agent; missing is a no-op."""
    with _database().transaction() as conn:
        conn.execute("DELETE FROM agent_admin_state WHERE agent_name = :name", {"name": agent_name})


def rename(old_name: str, new_name: str) -> None:
    """Re-key the side-table row when an agent is renamed; missing is a no-op."""
    with _database().transaction() as conn:
        conn.execute(
            "UPDATE agent_admin_state SET agent_name = :new, updated_at = :now"
            " WHERE agent_name = :old",
            {"new": new_name, "old": old_name, "now": _now()},
        )


_FIELDS = {"status", "provenance", "drift", "archived_at"}
_DEFAULTS = {"status": "enabled", "provenance": "adhoc", "drift": 0, "archived_at": None}


def _upsert(agent_name: str, fields: dict[str, Any]) -> None:
    merged = {**_DEFAULTS, **{k: v for k, v in fields.items() if k in _FIELDS}}
    assignments = ", ".join(f"{k} = :{k}" for k in fields if k in _FIELDS)
    params = {**merged, "agent_name": agent_name, "updated_at": _now()}
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_admin_state
                (agent_name, status, provenance, drift, archived_at, updated_at)
            VALUES (:agent_name, :status, :provenance, :drift, :archived_at, :updated_at)
            ON CONFLICT(agent_name) DO UPDATE SET {assignments}, updated_at = :updated_at
            """.replace("{assignments}", assignments),
            params,
        )
