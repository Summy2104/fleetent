from dataclasses import dataclass
from datetime import datetime

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database


@dataclass(frozen=True)
class AgentKnowledgeBaseBinding:
    """Explicit knowledge-base visibility binding for one agent."""

    tenant_id: str
    agent_id: str
    kb_id: str
    created_at: datetime


def resolve_agent_kb_ids(tenant_id: str, agent_id: str) -> list[str]:
    """Resolve the effective knowledge-base ids visible to an agent."""
    resolved_tenant_id = _require_non_empty("tenant_id", tenant_id)
    resolved_agent_id = _require_non_empty("agent_id", agent_id)
    bindings = _list_bindings_from_db(resolved_tenant_id, resolved_agent_id)
    if bindings:
        return [binding.kb_id for binding in bindings]

    default_kb_id = _kb_config().default_kb_id.strip()
    if default_kb_id:
        return [default_kb_id]

    return []


def _get_binding(
    database: SQLiteDatabase,
    tenant_id: str,
    agent_id: str,
    kb_id: str,
) -> AgentKnowledgeBaseBinding | None:
    row = database.execute(
        """
        SELECT tenant_id, agent_id, kb_id, created_at
        FROM knowledge_base_agent_bindings
        WHERE tenant_id = :tenant_id
          AND agent_id = :agent_id
          AND kb_id = :kb_id
        """,
        {"tenant_id": tenant_id, "agent_id": agent_id, "kb_id": kb_id},
    ).fetchone()
    return _row_to_binding(row) if row is not None else None


def _list_bindings_from_db(tenant_id: str, agent_id: str) -> list[AgentKnowledgeBaseBinding]:
    rows = (
        _database()
        .execute(
            """
        SELECT tenant_id, agent_id, kb_id, created_at
        FROM knowledge_base_agent_bindings
        WHERE tenant_id = :tenant_id
          AND agent_id = :agent_id
        ORDER BY kb_id ASC
        """,
            {"tenant_id": tenant_id, "agent_id": agent_id},
        )
        .fetchall()
    )
    return [_row_to_binding(row) for row in rows]


def _row_to_binding(row: dict[str, object]) -> AgentKnowledgeBaseBinding:
    return AgentKnowledgeBaseBinding(
        tenant_id=str(row["tenant_id"]),
        agent_id=str(row["agent_id"]),
        kb_id=str(row["kb_id"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )


def _require_non_empty(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _settings() -> Settings:
    return Settings()


def _kb_config() -> KnowledgeBaseSettings:
    return KnowledgeBaseSettings()


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)
