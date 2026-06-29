"""Management state for the Agent console: lifecycle status + default binding."""

import datetime
import sqlite3
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


def touch(agent_id: int) -> None:
    """Advance an agent's management-plane updated_at without changing other state."""
    try:
        _upsert(agent_id, {})
    except sqlite3.OperationalError as exc:
        if "no such table: agent_admin_state" not in str(exc):
            raise


def is_default(agent_id: int) -> bool:
    return bool(get_state(agent_id).get("is_default", 0))


def list_states(include_archived: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT
            agent_admin_state.agent_id,
            agents.name AS agent_name,
            agent_admin_state.status,
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
    im_groups = [
        {"platform": str(r["platform"]), "group_id": str(r["group_id"])}
        for r in db.execute(
            """
            SELECT platform, group_id
            FROM agent_im_groups
            WHERE agent_id = :aid
            ORDER BY platform, group_id
            """,
            {"aid": agent_id},
        ).fetchall()
    ]
    mcp_servers = [
        str(r["server_id"])
        for r in db.execute(
            """
            SELECT server_id
            FROM agent_mcp_servers
            WHERE agent_id = :aid
            ORDER BY server_id
            """,
            {"aid": agent_id},
        ).fetchall()
    ]
    kbs = [
        str(r["kb_id"])
        for r in db.execute(
            """
            SELECT kb_id
            FROM agent_kbs
            WHERE agent_id = :aid
            ORDER BY kb_id
            """,
            {"aid": agent_id},
        ).fetchall()
    ]
    placements = [
        str(r["node_id"])
        for r in db.execute(
            """
            SELECT node_id
            FROM agent_placements
            WHERE agent_id = :aid
            ORDER BY node_id
            """,
            {"aid": agent_id},
        ).fetchall()
    ]
    return {
        "users": users,
        "channels": [],
        "im_groups": im_groups,
        "mcp_servers": mcp_servers,
        "kbs": kbs,
        "service_grants": [],
        "placements": placements,
    }


def is_referenced(agent_id: int) -> bool:
    refs = references(agent_id)
    return any(bool(value) for value in refs.values())


def delete_state(agent_id: int) -> None:
    """Remove the side-table row for a hard-deleted agent; missing is a no-op."""
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM agent_admin_state WHERE agent_id = :agent_id", {"agent_id": agent_id}
        )


_FIELDS = {"status", "is_default", "archived_at"}
_DEFAULTS = {
    "status": "enabled",
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
    if not assignments:
        assignments = "agent_id = agent_id"
    params = {**merged, "agent_id": agent_id, "updated_at": _now()}
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_admin_state
                (agent_id, status, is_default, archived_at, updated_at)
            VALUES (:agent_id, :status, :is_default, :archived_at, :updated_at)
            ON CONFLICT(agent_id) DO UPDATE SET {assignments}, updated_at = :updated_at
            """.replace("{assignments}", assignments),
            params,
        )
