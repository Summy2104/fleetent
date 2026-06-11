"""Retention and compaction maintenance for User Memory."""

from __future__ import annotations

from fleetent import vector_store
from fleetent.memory import store
from fleetent.memory.models import (
    MemoryMaintenancePolicy,
    MemoryMaintenanceSummary,
)


async def run_memory_maintenance(
    user_id: str,
    *,
    policy: MemoryMaintenancePolicy | None = None,
    dry_run: bool = True,
) -> MemoryMaintenanceSummary:
    """Run per-user semantic memory retention and compaction maintenance."""
    policy = policy or MemoryMaintenancePolicy()
    validate_maintenance_request(user_id, policy)
    expired_ids = store.expired_context_ids(user_id)
    over_limit_ids = store.over_limit_ids(user_id, policy)
    compaction_candidates = (
        store.duplicate_compaction_candidates(user_id) if policy.compact_duplicates else []
    )
    duplicate_ids = [id for candidate in compaction_candidates for id in candidate.duplicate_ids]
    deleted_ids = dedupe_ids([*expired_ids, *over_limit_ids, *duplicate_ids])
    if not dry_run:
        for id in deleted_ids:
            store.delete_memory(user_id, id)
            await store.vector_backend().delete(id, vector_store.memory_namespace(user_id))
    return MemoryMaintenanceSummary(
        user_id=user_id,
        dry_run=dry_run,
        expired_count=len(expired_ids),
        over_limit_count=len(over_limit_ids),
        compacted_count=len(duplicate_ids),
        deleted_ids=deleted_ids,
        compaction_candidates=compaction_candidates,
    )


def validate_maintenance_request(user_id: str, policy: MemoryMaintenancePolicy) -> None:
    if not user_id.strip():
        raise ValueError("user_id must not be empty")
    limits = {
        "max_identity": policy.max_identity,
        "max_preferences": policy.max_preferences,
        "max_context": policy.max_context,
    }
    for name, limit in limits.items():
        if limit < 0:
            raise ValueError(f"{name} must be greater than or equal to 0")


def dedupe_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for id in ids:
        if id in seen:
            continue
        seen.add(id)
        result.append(id)
    return result
