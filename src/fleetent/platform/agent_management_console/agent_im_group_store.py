"""Per-agent IM group allowlist bindings (migration 088, db runtime, named params)."""

import datetime

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def bind(agent_id: int, platform: str, group_id: str, created_by: str | None = None) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_im_groups
                (agent_id, platform, group_id, created_at, created_by)
            VALUES (:agent_id, :platform, :group_id, :created_at, :created_by)
            """,
            {
                "agent_id": agent_id,
                "platform": platform,
                "group_id": group_id,
                "created_at": _now(),
                "created_by": created_by,
            },
        )


def unbind(agent_id: int, platform: str, group_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            DELETE FROM agent_im_groups
            WHERE agent_id = :agent_id AND platform = :platform AND group_id = :group_id
            """,
            {"agent_id": agent_id, "platform": platform, "group_id": group_id},
        )


def list_groups_for_agent(agent_id: int) -> list[dict[str, str]]:
    rows = (
        _database()
        .execute(
            """
            SELECT platform, group_id
            FROM agent_im_groups
            WHERE agent_id = :agent_id
            ORDER BY platform, group_id
            """,
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [{"platform": str(r["platform"]), "group_id": str(r["group_id"])} for r in rows]
