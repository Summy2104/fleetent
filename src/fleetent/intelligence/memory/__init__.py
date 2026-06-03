"""Public User Memory API."""

from __future__ import annotations

from fleetent.intelligence.memory.extraction import extract_and_update
from fleetent.intelligence.memory.maintenance import run_memory_maintenance
from fleetent.intelligence.memory.models import (
    MemoryCompactionCandidate,
    MemoryItem,
    MemoryMaintenancePolicy,
    MemoryMaintenanceSummary,
    MemoryType,
    SharedMemoryItem,
    SharedMemoryScopeType,
    SharedMemoryStatus,
    SharedMemoryType,
)
from fleetent.intelligence.memory.operations import (
    delete_user_memory,
    iter_indexable_memories,
    mark_user_memory_stale,
    merge_user_memories,
    update_user_memory_content,
)
from fleetent.intelligence.memory.search import search
from fleetent.intelligence.memory.shared import (
    apply_shared_memory_proposal,
    archive_shared_memory,
    create_shared_memory,
    iter_indexable_shared_memories,
    list_shared_memory,
    search_shared_memory,
    update_shared_memory,
)
from fleetent.intelligence.memory.trends import (
    MemoryQualityTrendBucket,
    MemoryQualityTrendQuery,
    MemoryQualityTrendSummary,
    get_memory_quality_trend_summary,
)

__all__ = [
    "MemoryCompactionCandidate",
    "MemoryItem",
    "MemoryMaintenancePolicy",
    "MemoryMaintenanceSummary",
    "MemoryQualityTrendBucket",
    "MemoryQualityTrendQuery",
    "MemoryQualityTrendSummary",
    "MemoryType",
    "SharedMemoryItem",
    "SharedMemoryScopeType",
    "SharedMemoryStatus",
    "SharedMemoryType",
    "apply_shared_memory_proposal",
    "archive_shared_memory",
    "create_shared_memory",
    "delete_user_memory",
    "extract_and_update",
    "get_memory_quality_trend_summary",
    "iter_indexable_shared_memories",
    "iter_indexable_memories",
    "list_shared_memory",
    "mark_user_memory_stale",
    "merge_user_memories",
    "run_memory_maintenance",
    "search",
    "search_shared_memory",
    "update_shared_memory",
    "update_user_memory_content",
]
