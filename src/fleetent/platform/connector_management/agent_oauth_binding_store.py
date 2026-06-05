"""Per-agent OAuth connector bindings (migration 045, db runtime, named params, no ORM).

Each row is a join: "agent X may use OAuth connector Y". Parallels the agent MCP
server bindings; the connector catalog itself lives in connector_config_store. This is
authoring metadata only — runtime consumption is a separate follow-up.
"""

import datetime

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def bind(agent_id: int, connector_id: str, created_by: str | None = None) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO agent_oauth_bindings "
            "(agent_id, connector_id, created_at, created_by) "
            "VALUES (:agent_id, :connector_id, :created_at, :created_by)",
            {
                "agent_id": agent_id,
                "connector_id": connector_id,
                "created_at": _now(),
                "created_by": created_by,
            },
        )


def unbind(agent_id: int, connector_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM agent_oauth_bindings "
            "WHERE agent_id = :agent_id AND connector_id = :connector_id",
            {"agent_id": agent_id, "connector_id": connector_id},
        )


def list_connectors_for_agent(agent_id: int) -> list[str]:
    rows = (
        _database()
        .execute(
            "SELECT connector_id FROM agent_oauth_bindings "
            "WHERE agent_id = :agent_id ORDER BY connector_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [str(r["connector_id"]) for r in rows]


def list_agents_for_connector(connector_id: str) -> list[int]:
    rows = (
        _database()
        .execute(
            "SELECT agent_id FROM agent_oauth_bindings "
            "WHERE connector_id = :connector_id ORDER BY agent_id",
            {"connector_id": connector_id},
        )
        .fetchall()
    )
    return [int(r["agent_id"]) for r in rows]
