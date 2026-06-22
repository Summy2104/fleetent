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
                agent_admin_state.is_default,
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
            "is_default": 0,
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


def set_default(agent_id: int) -> None:
    tenant_id = _agent_tenant(agent_id)
    if tenant_id is None:
        raise ValueError(f"agent not found: {agent_id}")
    with _database().transaction() as conn:
        conn.execute(
            """
            UPDATE agent_admin_state
            SET is_default = 0, updated_at = :updated_at
            WHERE agent_id IN (
                SELECT id FROM agents WHERE tenant_id = :tenant_id
            )
            """,
            {"tenant_id": tenant_id, "updated_at": _now()},
        )
    _upsert(agent_id, {"is_default": 1})


def clear_default() -> None:
    _database().execute(
        "UPDATE agent_admin_state SET is_default = 0, updated_at = :updated_at",
        {"updated_at": _now()},
    )


def is_default(agent_id: int) -> bool:
    return bool(get_state(agent_id).get("is_default", 0))


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
            agent_admin_state.is_default,
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
    return {"users": users, "channels": []}


def is_referenced(agent_id: int) -> bool:
    refs = references(agent_id)
    return bool(refs["users"] or refs["channels"])


def delete_state(agent_id: int) -> None:
    """Remove the side-table row for a hard-deleted agent; missing is a no-op."""
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM agent_admin_state WHERE agent_id = :agent_id", {"agent_id": agent_id}
        )


_FIELDS = {"status", "provenance", "drift", "is_default", "archived_at"}
_DEFAULTS = {
    "status": "enabled",
    "provenance": "adhoc",
    "drift": 0,
    "is_default": 0,
    "archived_at": None,
}


def _agent_name(agent_id: int) -> str | None:
    row = (
        _database()
        .execute("SELECT name FROM agents WHERE id = :agent_id", {"agent_id": agent_id})
        .fetchone()
    )
    return None if row is None else str(row["name"])


def _agent_tenant(agent_id: int) -> str | None:
    row = (
        _database()
        .execute("SELECT tenant_id FROM agents WHERE id = :agent_id", {"agent_id": agent_id})
        .fetchone()
    )
    return None if row is None else str(row["tenant_id"])


def _upsert(agent_id: int, fields: dict[str, Any]) -> None:
    merged = {**_DEFAULTS, **{k: v for k, v in fields.items() if k in _FIELDS}}
    assignments = ", ".join(f"{k} = :{k}" for k in fields if k in _FIELDS)
    params = {**merged, "agent_id": agent_id, "updated_at": _now()}
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_admin_state
                (agent_id, status, provenance, drift, is_default, archived_at, updated_at)
            VALUES (:agent_id, :status, :provenance, :drift, :is_default, :archived_at, :updated_at)
            ON CONFLICT(agent_id) DO UPDATE SET {assignments}, updated_at = :updated_at
            """.replace("{assignments}", assignments),
            params,
        )
