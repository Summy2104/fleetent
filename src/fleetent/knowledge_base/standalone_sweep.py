from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fleetent import kb_ingest_jobs
from fleetent.knowledge_base.service_config import KBServiceConfig

logger = logging.getLogger(__name__)


def is_connector_due(row: dict[str, Any], now: datetime) -> bool:
    if not row.get("enabled"):
        return False
    interval = row.get("sync_interval_seconds")
    if interval is None:
        return False
    last_raw = row.get("last_scheduled_sync_at")
    if last_raw is None:
        return True
    try:
        last = datetime.fromisoformat(str(last_raw))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (now - last).total_seconds() >= float(interval)
    except (TypeError, ValueError):
        return True


def sweep(
    config: KBServiceConfig,
    *,
    queue_database_url: str | None = None,
    now: datetime | None = None,
) -> None:
    database_url = queue_database_url or config.queue_database_url()
    current = now or datetime.now(UTC)
    for row in config.connector_rows():
        connector_id = str(row["connector_id"])
        enriched = dict(row)
        enriched["last_scheduled_sync_at"] = kb_ingest_jobs.get_last_scheduled_sync_at(
            connector_id,
            database_url=database_url,
        )
        if not is_connector_due(enriched, current):
            continue
        try:
            kb_ingest_jobs.enqueue_connector_job(enriched, database_url=database_url)
            kb_ingest_jobs.mark_connector_scheduled(
                connector_id,
                current.isoformat(),
                database_url=database_url,
            )
        except Exception:
            logger.exception("standalone_kb_sweep_enqueue_failed connector_id=%s", connector_id)
