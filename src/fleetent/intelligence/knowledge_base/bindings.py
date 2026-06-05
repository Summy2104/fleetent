from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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


def bind_agent_to_kb(
    tenant_id: str,
    agent_id: str,
    kb_id: str,
) -> AgentKnowledgeBaseBinding:
    """Bind an agent to a knowledge base, idempotently."""
    resolved_tenant_id = _require_non_empty("tenant_id", tenant_id)
    resolved_agent_id = _require_non_empty("agent_id", agent_id)
    resolved_kb_id = _require_non_empty("kb_id", kb_id)
    database = _database()
    created_at = _now()
    database.execute(
        """
        INSERT OR IGNORE INTO knowledge_base_agent_bindings (
            tenant_id, agent_id, kb_id, created_at
        )
        VALUES (:tenant_id, :agent_id, :kb_id, :created_at)
        """,
        {
            "tenant_id": resolved_tenant_id,
            "agent_id": resolved_agent_id,
            "kb_id": resolved_kb_id,
            "created_at": created_at.isoformat(),
        },
    )
    binding = _get_binding(database, resolved_tenant_id, resolved_agent_id, resolved_kb_id)
    if binding is None:
        raise RuntimeError("agent knowledge-base binding was not persisted")
    return binding


def unbind_agent_from_kb(tenant_id: str, agent_id: str, kb_id: str) -> None:
    """Remove an agent knowledge-base binding, idempotently."""
    resolved_tenant_id = _require_non_empty("tenant_id", tenant_id)
    resolved_agent_id = _require_non_empty("agent_id", agent_id)
    resolved_kb_id = _require_non_empty("kb_id", kb_id)
    _database().execute(
        """
        DELETE FROM knowledge_base_agent_bindings
        WHERE tenant_id = :tenant_id
          AND agent_id = :agent_id
          AND kb_id = :kb_id
        """,
        {
            "tenant_id": resolved_tenant_id,
            "agent_id": resolved_agent_id,
            "kb_id": resolved_kb_id,
        },
    )


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


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _settings() -> Settings:
    return Settings()


def _kb_config() -> KnowledgeBaseSettings:
    """knowledge_base config from the active agent (a neutral default when absent)."""
    from fleetent import agent_config

    return agent_config.active_agent_or_default().knowledge_base


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)
