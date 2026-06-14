"""Management-face persistence for the KB↔Agent binding matrix.

db runtime + named params, no ORM. KB / document / chunk main tables belong to the
knowledge-base engine; this module owns only which KBs are bound to which agents
(consumed by long-term-ctx to scope retrieval per agent, and by the admin console's
delete-protection on KB archive). Tenancy: (tenant_id, kb_id, agent_id) is unique.
"""

import datetime

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def bind(tenant_id: str, kb_id: str, agent_id: int, created_by: str | None = None) -> None:
    """Bind a KB to an agent (idempotent on the composite key)."""
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_kbs (tenant_id, kb_id, agent_id, created_at, created_by)
            VALUES (:tenant_id, :kb_id, :agent_id, :created_at, :created_by)
            ON CONFLICT(tenant_id, kb_id, agent_id) DO NOTHING
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "agent_id": agent_id,
                "created_at": _now(),
                "created_by": created_by,
            },
        )


def unbind(tenant_id: str, kb_id: str, agent_id: int) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM agent_kbs WHERE tenant_id = :tenant_id AND kb_id = :kb_id "
            "AND agent_id = :agent_id",
            {"tenant_id": tenant_id, "kb_id": kb_id, "agent_id": agent_id},
        )


def list_agents_for_kb(tenant_id: str, kb_id: str) -> list[int]:
    rows = (
        _database()
        .execute(
            "SELECT agent_id FROM agent_kbs WHERE tenant_id = :tenant_id AND kb_id = :kb_id "
            "ORDER BY agent_id",
            {"tenant_id": tenant_id, "kb_id": kb_id},
        )
        .fetchall()
    )
    return [r["agent_id"] for r in rows]


def list_kbs_for_agent(tenant_id: str, agent_id: int) -> list[str]:
    rows = (
        _database()
        .execute(
            "SELECT kb_id FROM agent_kbs WHERE tenant_id = :tenant_id AND agent_id = :agent_id "
            "ORDER BY kb_id",
            {"tenant_id": tenant_id, "agent_id": agent_id},
        )
        .fetchall()
    )
    return [r["kb_id"] for r in rows]


def is_kb_bound(tenant_id: str, kb_id: str) -> bool:
    """True when at least one agent is bound to the KB — drives KB archive protection."""
    row = (
        _database()
        .execute(
            "SELECT 1 FROM agent_kbs WHERE tenant_id = :tenant_id AND kb_id = :kb_id LIMIT 1",
            {"tenant_id": tenant_id, "kb_id": kb_id},
        )
        .fetchone()
    )
    return row is not None
