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
)
from fleetent.intelligence.memory.operations import (
    delete_user_memory,
    iter_indexable_memories,
    mark_user_memory_stale,
    merge_user_memories,
    update_user_memory_content,
)
from fleetent.intelligence.memory.search import search

__all__ = [
    "MemoryCompactionCandidate",
    "MemoryItem",
    "MemoryMaintenancePolicy",
    "MemoryMaintenanceSummary",
    "MemoryType",
    "delete_user_memory",
    "extract_and_update",
    "iter_indexable_memories",
    "mark_user_memory_stale",
    "merge_user_memories",
    "run_memory_maintenance",
    "search",
    "update_user_memory_content",
]
