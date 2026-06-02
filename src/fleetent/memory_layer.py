"""Compatibility shim for the User Memory public API."""

from __future__ import annotations

from fleetent.intelligence.memory import (
    MemoryCompactionCandidate,
    MemoryItem,
    MemoryMaintenancePolicy,
    MemoryMaintenanceSummary,
    MemoryType,
    delete_user_memory,
    extract_and_update,
    iter_indexable_memories,
    mark_user_memory_stale,
    merge_user_memories,
    run_memory_maintenance,
    search,
    update_user_memory_content,
)

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
