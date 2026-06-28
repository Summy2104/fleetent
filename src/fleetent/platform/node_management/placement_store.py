"""Management-plane persistence for agent-to-node placements."""

from __future__ import annotations

import datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_COLS = "agent_id, node_id, pinned_at, pinned_by, updated_at"


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def pin_agent(agent_id: int, node_id: str, *, pinned_by: str | None = None) -> dict[str, Any]:
    if not _agent_exists(agent_id):
        raise ValueError(f"agent {agent_id} not found")
    if not _node_exists(node_id):
        raise ValueError(f"node {node_id!r} not found")
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_placements (agent_id, node_id, pinned_at, pinned_by, updated_at)
            VALUES (:agent_id, :node_id, :pinned_at, :pinned_by, :updated_at)
            ON CONFLICT(agent_id) DO UPDATE SET
                node_id = excluded.node_id,
                pinned_at = excluded.pinned_at,
                pinned_by = excluded.pinned_by,
                updated_at = excluded.updated_at
            """,
            {
                "agent_id": agent_id,
                "node_id": node_id,
                "pinned_at": now,
                "pinned_by": pinned_by,
                "updated_at": now,
            },
        )
    placement = get_for_agent(agent_id)
    assert placement is not None
    return placement


def unpin_agent(agent_id: int) -> None:
    with _database().transaction() as conn:
        conn.execute("DELETE FROM agent_placements WHERE agent_id = :agent_id", {"agent_id": agent_id})
        conn.execute(
            "DELETE FROM node_agent_status WHERE agent_id = :agent_id",
            {"agent_id": agent_id},
        )


def list_by_node(node_id: str) -> list[dict[str, Any]]:
    rows = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM agent_placements WHERE node_id = :node_id ORDER BY agent_id",
            {"node_id": node_id},
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def list_placements() -> list[dict[str, Any]]:
    """Read every agent→node placement (read-only)."""
    rows = _database().execute(f"SELECT {_COLS} FROM agent_placements ORDER BY agent_id").fetchall()
    return [dict(row) for row in rows]


def get_for_agent(agent_id: int) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM agent_placements WHERE agent_id = :agent_id",
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    return dict(row) if row else None


def _agent_exists(agent_id: int) -> bool:
    row = (
        _database()
        .execute("SELECT 1 AS present FROM agents WHERE id = :agent_id", {"agent_id": agent_id})
        .fetchone()
    )
    return row is not None


def _node_exists(node_id: str) -> bool:
    row = (
        _database()
        .execute("SELECT 1 AS present FROM nodes WHERE id = :node_id", {"node_id": node_id})
        .fetchone()
    )
    return row is not None
