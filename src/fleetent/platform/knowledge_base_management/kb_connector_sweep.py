"""KB connector scheduled-sync sweep.

Runs in the platform process (cron_scheduler) to enqueue due connectors into the
kb_ingest_jobs queue.  The existing worker drains the queue and calls
run_connector_sync — this module only decides *when* to enqueue, never changes
the worker or sync logic.

Dedup: advancing last_scheduled_sync_at immediately after enqueue means the next
tick finds the connector within its interval and skips it.  A failed sync is not
tracked here; the next due tick will naturally retry (no state-machine needed).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fleetent import kb_ingest_jobs
from fleetent.platform.knowledge_base_management.kb_connector_store import (
    list_schedulable_connectors,
    update_last_scheduled_sync_at,
)

logger = logging.getLogger(__name__)

# Re-export for easy patching in tests
enqueue_connector_job = kb_ingest_jobs.enqueue_connector_job


def is_connector_due(row: dict[str, Any], now: datetime) -> bool:
    """Return True when a connector should be enqueued on this sweep tick."""
    if not row.get("enabled"):
        return False
    interval = row.get("sync_interval_seconds")
    if interval is None:
        return False
    last_raw = row.get("last_scheduled_sync_at")
    if last_raw is None:
        return True
    try:
        last = datetime.fromisoformat(last_raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds()
        return elapsed >= interval
    except (ValueError, TypeError):
        return True


def sweep() -> None:
    """Enqueue all due connectors; best-effort — a single failure never aborts the sweep."""
    now = datetime.now(UTC)
    connectors = list_schedulable_connectors()
    for row in connectors:
        connector_id = row["connector_id"]
        if not is_connector_due(row, now):
            continue
        try:
            enqueue_connector_job(row)
            update_last_scheduled_sync_at(connector_id, now.isoformat())
        except Exception:
            logger.exception("kb_connector_sweep_enqueue_failed connector_id=%s", connector_id)
