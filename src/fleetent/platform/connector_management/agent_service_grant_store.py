"""Per-agent external service grants."""

from __future__ import annotations

import datetime
from typing import Literal

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

RunAs = Literal["user", "agent"]


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def bind(
    agent_id: int,
    service_id: str,
    *,
    run_as: RunAs = "user",
    created_by: str | None = None,
) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_service_grants (agent_id, service_id, run_as, created_at, created_by)
            VALUES (:agent_id, :service_id, :run_as, :created_at, :created_by)
            ON CONFLICT(agent_id, service_id) DO UPDATE SET
                run_as = excluded.run_as,
                created_by = excluded.created_by
            """,
            {
                "agent_id": agent_id,
                "service_id": service_id,
                "run_as": run_as,
                "created_at": _now(),
                "created_by": created_by,
            },
        )


def unbind(agent_id: int, service_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            DELETE FROM agent_service_grants
            WHERE agent_id = :agent_id AND service_id = :service_id
            """,
            {"agent_id": agent_id, "service_id": service_id},
        )


def list_services_for_agent(agent_id: int) -> list[dict[str, str]]:
    rows = (
        _database()
        .execute(
            """
            SELECT service_id, run_as
            FROM agent_service_grants
            WHERE agent_id = :agent_id
            ORDER BY service_id
            """,
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [{"service_id": str(row["service_id"]), "run_as": str(row["run_as"])} for row in rows]


def list_agents_for_service(service_id: str) -> list[int]:
    rows = (
        _database()
        .execute(
            """
            SELECT agent_id
            FROM agent_service_grants
            WHERE service_id = :service_id
            ORDER BY agent_id
            """,
            {"service_id": service_id},
        )
        .fetchall()
    )
    return [int(row["agent_id"]) for row in rows]
