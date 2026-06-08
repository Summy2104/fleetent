from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalDirectorySourceConfig:
    """Configuration for a manual local directory sync."""

    source_id: str
    root_path: str | Path
    allowed_roots: list[str | Path]


@dataclass(frozen=True)
class LocalSyncSummary:
    """Counts returned by a manual local directory sync."""

    scanned: int
    ingested: int
    skipped: int
    failed: int
    unsupported: int = 0
    unchanged: int = 0
    deleted: int = 0


async def sync_local_directory(
    config: LocalDirectorySourceConfig,
    tenant_id: str,
    kb_id: str,
) -> LocalSyncSummary:
    """Manually import supported files from an allowlisted local directory."""

    from fleetent.knowledge_base.sync_planner import (
        execute_sync_plan,
        plan_local_directory_sync,
    )

    plan = await plan_local_directory_sync(config, tenant_id=tenant_id, kb_id=kb_id)
    summary = await execute_sync_plan(plan)
    return LocalSyncSummary(
        scanned=summary.scanned,
        ingested=summary.ingested,
        skipped=summary.skipped,
        failed=summary.failed,
        unsupported=summary.unsupported,
        unchanged=summary.unchanged,
        deleted=summary.deleted,
    )
