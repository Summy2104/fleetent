"""Long-term context policy: tenant-default + agent-override persistence.

The stored model is a wide row per scope controlling source enablement and
per-source budgets for User Memory, Shared Memory (tenant/team), and Knowledge
Base. Tenant-default rows use an empty-string ``agent_id`` sentinel so the
unique scope index enforces a single default per tenant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_CONFLICT_PREFERENCES = {"auto", "memory", "knowledge"}
_TENANT_DEFAULT_AGENT = ""

_COLUMNS = (
    "tenant_id",
    "agent_id",
    "user_memory_enabled",
    "tenant_shared_memory_enabled",
    "team_shared_memory_enabled",
    "knowledge_base_enabled",
    "user_memory_max_tokens",
    "user_memory_top_k",
    "tenant_shared_memory_max_tokens",
    "tenant_shared_memory_top_k",
    "team_shared_memory_max_tokens",
    "team_shared_memory_top_k",
    "knowledge_base_max_tokens",
    "knowledge_base_top_k",
    "conflict_preference",
)

_BUDGET_FIELDS = (
    "user_memory_max_tokens",
    "tenant_shared_memory_max_tokens",
    "team_shared_memory_max_tokens",
    "knowledge_base_max_tokens",
)
_TOP_K_FIELDS = (
    "user_memory_top_k",
    "tenant_shared_memory_top_k",
    "team_shared_memory_top_k",
    "knowledge_base_top_k",
)


@dataclass(frozen=True)
class ContextPolicyRecord:
    """One stored policy scope (tenant default when ``agent_id`` is None)."""

    tenant_id: str
    agent_id: str | None
    user_memory_enabled: bool
    tenant_shared_memory_enabled: bool
    team_shared_memory_enabled: bool
    knowledge_base_enabled: bool
    user_memory_max_tokens: int
    user_memory_top_k: int
    tenant_shared_memory_max_tokens: int
    tenant_shared_memory_top_k: int
    team_shared_memory_max_tokens: int
    team_shared_memory_top_k: int
    knowledge_base_max_tokens: int
    knowledge_base_top_k: int
    conflict_preference: str


def upsert_policy(record: ContextPolicyRecord) -> ContextPolicyRecord:
    """Insert or replace a policy scope after validating it."""
    validate_policy_record(record)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    agent_key = record.agent_id if record.agent_id is not None else _TENANT_DEFAULT_AGENT
    params: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_key,
        "created_at": now,
        "updated_at": now,
        **{name: getattr(record, name) for name in _COLUMNS if name != "agent_id"},
    }
    for name in (
        "user_memory_enabled",
        "tenant_shared_memory_enabled",
        "team_shared_memory_enabled",
        "knowledge_base_enabled",
    ):
        params[name] = int(bool(params[name]))
    columns = ", ".join(["id", *_COLUMNS, "created_at", "updated_at"])
    placeholders = ", ".join(f":{name}" for name in ["id", *_COLUMNS, "created_at", "updated_at"])
    _database().execute(
        f"""
        INSERT INTO long_term_context_policies ({columns})
        VALUES ({placeholders})
        ON CONFLICT(tenant_id, agent_id) DO UPDATE SET
            user_memory_enabled = excluded.user_memory_enabled,
            tenant_shared_memory_enabled = excluded.tenant_shared_memory_enabled,
            team_shared_memory_enabled = excluded.team_shared_memory_enabled,
            knowledge_base_enabled = excluded.knowledge_base_enabled,
            user_memory_max_tokens = excluded.user_memory_max_tokens,
            user_memory_top_k = excluded.user_memory_top_k,
            tenant_shared_memory_max_tokens = excluded.tenant_shared_memory_max_tokens,
            tenant_shared_memory_top_k = excluded.tenant_shared_memory_top_k,
            team_shared_memory_max_tokens = excluded.team_shared_memory_max_tokens,
            team_shared_memory_top_k = excluded.team_shared_memory_top_k,
            knowledge_base_max_tokens = excluded.knowledge_base_max_tokens,
            knowledge_base_top_k = excluded.knowledge_base_top_k,
            conflict_preference = excluded.conflict_preference,
            updated_at = excluded.updated_at
        """,
        params,
    )
    return record


def get_policy(tenant_id: str, agent_id: str | None) -> ContextPolicyRecord | None:
    """Load one policy scope, or None when no row exists."""
    agent_key = agent_id if agent_id is not None else _TENANT_DEFAULT_AGENT
    row = (
        _database()
        .execute(
            """
            SELECT *
            FROM long_term_context_policies
            WHERE tenant_id = :tenant_id AND agent_id = :agent_id
            """,
            {"tenant_id": tenant_id, "agent_id": agent_key},
        )
        .fetchone()
    )
    if row is None:
        return None
    return _row_to_record(row)


def validate_policy_record(record: ContextPolicyRecord) -> None:
    """Reject empty tenant, invalid budgets/top-k, or unknown conflict preference."""
    if not record.tenant_id.strip():
        raise ValueError("tenant_id must not be empty")
    if record.agent_id is not None and not record.agent_id.strip():
        raise ValueError("agent_id must not be empty when provided")
    for name in _BUDGET_FIELDS:
        if getattr(record, name) < 0:
            raise ValueError(f"{name} must not be negative")
    for name in _TOP_K_FIELDS:
        if getattr(record, name) < 0:
            raise ValueError(f"{name} must not be negative")
    if record.conflict_preference not in _CONFLICT_PREFERENCES:
        raise ValueError("conflict_preference must be auto, memory, or knowledge")


def _row_to_record(row: dict[str, Any]) -> ContextPolicyRecord:
    agent_id = str(row["agent_id"])
    return ContextPolicyRecord(
        tenant_id=str(row["tenant_id"]),
        agent_id=agent_id if agent_id != _TENANT_DEFAULT_AGENT else None,
        user_memory_enabled=bool(row["user_memory_enabled"]),
        tenant_shared_memory_enabled=bool(row["tenant_shared_memory_enabled"]),
        team_shared_memory_enabled=bool(row["team_shared_memory_enabled"]),
        knowledge_base_enabled=bool(row["knowledge_base_enabled"]),
        user_memory_max_tokens=int(row["user_memory_max_tokens"]),
        user_memory_top_k=int(row["user_memory_top_k"]),
        tenant_shared_memory_max_tokens=int(row["tenant_shared_memory_max_tokens"]),
        tenant_shared_memory_top_k=int(row["tenant_shared_memory_top_k"]),
        team_shared_memory_max_tokens=int(row["team_shared_memory_max_tokens"]),
        team_shared_memory_top_k=int(row["team_shared_memory_top_k"]),
        knowledge_base_max_tokens=int(row["knowledge_base_max_tokens"]),
        knowledge_base_top_k=int(row["knowledge_base_top_k"]),
        conflict_preference=str(row["conflict_preference"]),
    )


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)
