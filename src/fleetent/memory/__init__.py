"""Public User Memory API.

The free-text ``search``/``extract_and_update`` interface is deprecated by
user-memory-v2: it now warns and no-ops.  Use the triple-based facts API —
``run_pipeline`` (write) and ``search_facts`` (read), plus ``pin_fact`` /
``retract_fact`` for user-initiated lifecycle.
"""

from __future__ import annotations

import warnings
from typing import Any

from fleetent.memory.agent_memory import (
    apply_agent_memory_proposal,
    archive_agent_memory,
    create_agent_memory,
    iter_indexable_agent_memories,
    list_agent_memory,
    search_agent_memory,
    update_agent_memory,
)
from fleetent.memory.facts_lifecycle import pin_fact, retract_fact
from fleetent.memory.facts_pipeline import run_pipeline
from fleetent.memory.facts_store import list_active_facts, set_facts_db
from fleetent.memory.maintenance import run_memory_maintenance
from fleetent.memory.models import (
    AgentMemoryItem,
    AgentMemorySource,
    AgentMemoryStatus,
    AgentMemoryType,
    MemoryCompactionCandidate,
    MemoryItem,
    MemoryMaintenancePolicy,
    MemoryMaintenanceSummary,
    MemoryType,
)
from fleetent.memory.operations import (
    delete_user_memory,
    iter_indexable_memories,
    mark_user_memory_stale,
    merge_user_memories,
    update_user_memory_content,
)
from fleetent.memory.trends import (
    MemoryQualityTrendBucket,
    MemoryQualityTrendQuery,
    MemoryQualityTrendSummary,
    get_memory_quality_trend_summary,
)


async def search_facts(
    user_id: str, query: str, *, limit: int = 10, subject: str | None = None
) -> list[Any]:
    """Retrieve relevant active facts for a user.

    Convenience wrapper that pulls the per-agent vector backend injected at boot
    (via ``set_facts_db``) so callers need not thread the backend through.  Pass
    ``subject`` (e.g. "user") to restrict to one fact subject.
    """
    from fleetent.memory import facts_search, facts_store

    return await facts_search.search_facts(
        user_id,
        query,
        limit=limit,
        subject=subject,
        vector_backend=facts_store._facts_vector_backend,
    )


def search(*args: Any, **kwargs: Any) -> list[MemoryItem]:
    """Deprecated: the free-text search is replaced by ``search_facts``.

    Returns an empty list rather than converting formats, to avoid silently
    feeding the old free-text shape to callers expecting facts.
    """
    warnings.warn(
        "memory.search() is deprecated by user-memory-v2; use memory.search_facts()",
        DeprecationWarning,
        stacklevel=2,
    )
    return []


async def extract_and_update(*args: Any, **kwargs: Any) -> None:
    """Deprecated: the free-text extraction is replaced by ``run_pipeline``."""
    warnings.warn(
        "memory.extract_and_update() is deprecated by user-memory-v2; use memory.run_pipeline()",
        DeprecationWarning,
        stacklevel=2,
    )


__all__ = [
    "AgentMemoryItem",
    "AgentMemorySource",
    "AgentMemoryStatus",
    "AgentMemoryType",
    "MemoryCompactionCandidate",
    "MemoryItem",
    "MemoryMaintenancePolicy",
    "MemoryMaintenanceSummary",
    "MemoryQualityTrendBucket",
    "MemoryQualityTrendQuery",
    "MemoryQualityTrendSummary",
    "MemoryType",
    "apply_agent_memory_proposal",
    "archive_agent_memory",
    "create_agent_memory",
    "delete_user_memory",
    "extract_and_update",
    "get_memory_quality_trend_summary",
    "iter_indexable_agent_memories",
    "iter_indexable_memories",
    "list_agent_memory",
    "list_active_facts",
    "mark_user_memory_stale",
    "merge_user_memories",
    "pin_fact",
    "retract_fact",
    "run_memory_maintenance",
    "run_pipeline",
    "search",
    "search_agent_memory",
    "search_facts",
    "set_facts_db",
    "update_agent_memory",
    "update_user_memory_content",
]
