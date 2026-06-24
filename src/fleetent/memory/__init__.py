"""Public User Memory API."""

from __future__ import annotations

from fleetent.memory.agent_memory import (
    apply_agent_memory_proposal,
    archive_agent_memory,
    create_agent_memory,
    iter_indexable_agent_memories,
    list_agent_memory,
    search_agent_memory,
    update_agent_memory,
)
from fleetent.memory.extraction import extract_and_update
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
from fleetent.memory.search import search
from fleetent.memory.trends import (
    MemoryQualityTrendBucket,
    MemoryQualityTrendQuery,
    MemoryQualityTrendSummary,
    get_memory_quality_trend_summary,
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
    "mark_user_memory_stale",
    "merge_user_memories",
    "run_memory_maintenance",
    "search",
    "search_agent_memory",
    "update_agent_memory",
    "update_user_memory_content",
]
