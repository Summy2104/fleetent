"""Compatibility shim for the renamed agent service grant store."""

from __future__ import annotations

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
            """
            INSERT INTO agent_service_grants (agent_id, service_id, run_as, created_at, created_by)
            VALUES (:agent_id, :service_id, 'user', :created_at, :created_by)
            ON CONFLICT(agent_id, service_id) DO NOTHING
            """,
            {
                "agent_id": agent_id,
                "service_id": connector_id,
                "created_at": _now(),
                "created_by": created_by,
            },
        )


def unbind(agent_id: int, connector_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            DELETE FROM agent_service_grants
            WHERE agent_id = :agent_id AND service_id = :service_id
            """,
            {"agent_id": agent_id, "service_id": connector_id},
        )


def list_connectors_for_agent(agent_id: int) -> list[str]:
    rows = (
        _database()
        .execute(
            """
            SELECT service_id
            FROM agent_service_grants
            WHERE agent_id = :agent_id
            ORDER BY service_id
            """,
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [str(row["service_id"]) for row in rows]


def list_agents_for_connector(connector_id: str) -> list[int]:
    rows = (
        _database()
        .execute(
            """
            SELECT agent_id
            FROM agent_service_grants
            WHERE service_id = :service_id
            ORDER BY agent_id
            """,
            {"service_id": connector_id},
        )
        .fetchall()
    )
    return [int(row["agent_id"]) for row in rows]
