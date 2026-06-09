from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.observability import TraceEvent, record_trace_event


@dataclass(frozen=True)
class AgentKnowledgeBaseBinding:
    """Explicit knowledge-base visibility binding for one agent."""

    tenant_id: str
    agent_id: str
    kb_id: str
    created_at: datetime


def list_agent_kb_bindings(tenant_id: str, agent_id: str) -> list[AgentKnowledgeBaseBinding]:
    """List explicit knowledge-base bindings for an agent."""
    resolved_tenant_id = _require_non_empty("tenant_id", tenant_id)
    resolved_agent_id = _require_non_empty("agent_id", agent_id)
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
            {"tenant_id": resolved_tenant_id, "agent_id": resolved_agent_id},
        )
        .fetchall()
    )
    return [_row_to_binding(row) for row in rows]


def resolve_agent_kb_ids(tenant_id: str, agent_id: str) -> list[str]:
    """Resolve the effective knowledge-base ids visible to an agent."""
    resolved_tenant_id = _require_non_empty("tenant_id", tenant_id)
    resolved_agent_id = _require_non_empty("agent_id", agent_id)
    bindings = list_agent_kb_bindings(resolved_tenant_id, resolved_agent_id)
    if bindings:
        return [binding.kb_id for binding in bindings]

    default_kb_id = _kb_config().default_kb_id.strip()
    if default_kb_id:
        return [default_kb_id]

    _record_empty_scope_diagnostic(
        tenant_id=resolved_tenant_id,
        agent_id=resolved_agent_id,
        reason="default_kb_missing",
    )
    return []


def _record_empty_scope_diagnostic(*, tenant_id: str, agent_id: str, reason: str) -> None:
    try:
        record_trace_event(
            TraceEvent(
                run_id=f"agent-kb-scope:{tenant_id}:{agent_id}",
                event_type="knowledge_base.agent_kb_scope_empty",
                tenant_id=tenant_id,
                agent_id=agent_id,
                payload={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "reason": reason,
                },
            )
        )
    except Exception:
        return


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
    """Neutral KB binding defaults; Agent-side access lives in agent.knowledge."""
    return KnowledgeBaseSettings()


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)
