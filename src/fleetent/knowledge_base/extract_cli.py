from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fleetent import kb_ingest_jobs
from fleetent.knowledge_base.management.runtime import list_documents, set_extraction_enabled
from fleetent.knowledge_base.service_config import load_kb_service_config
from fleetent.knowledge_base.worker import _knowledge_database, _require_active_kb

_POLL_INTERVAL_SECONDS = 0.25
_WAIT_TIMEOUT_SECONDS = 30.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb-extract")
    parser.add_argument("--config", required=True, help="standalone kb-service.yaml path")
    parser.add_argument("--kb", required=True, help="target knowledge base id")
    parser.add_argument("--wait", action="store_true", help="wait for the queued jobs to finish")
    return parser.parse_args(argv)


def _require_known_kb(tenant_id: str, kb_id: str, *, data_dir: Path) -> None:
    try:
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir)
    except ValueError as exc:
        raise ValueError(
            f"KB {kb_id!r} does not exist for tenant {tenant_id!r}. "
            "Create it first via POST /admin/kb."
        ) from exc


def _print_summary(*, documents: int, entities: int, relations: int) -> None:
    print(f"documents={documents} entities={entities} relations={relations}")


def _wait_for_jobs(
    job_ids: list[str],
    *,
    database_url: str,
    timeout_seconds: float = _WAIT_TIMEOUT_SECONDS,
) -> None:
    started_at = time.monotonic()
    pending_job_ids = set(job_ids)
    documents = 0
    entities = 0
    relations = 0

    while pending_job_ids:
        for job_id in list(pending_job_ids):
            job = kb_ingest_jobs.get_job(job_id, database_url=database_url)
            if job is None:
                print(f"job {job_id} disappeared from queue", file=sys.stderr)
                raise SystemExit(1)

            status = str(job["status"])
            if status in {"pending", "claimed"}:
                continue

            result = kb_ingest_jobs.get_job_result(job) or {}
            documents += int(result.get("documents_scanned", 0))
            entities += int(result.get("entities_upserted", 0))
            relations += int(result.get("relations_written", 0))
            pending_job_ids.remove(job_id)

            if status == "failed":
                _print_summary(documents=documents, entities=entities, relations=relations)
                last_error = str(job.get("last_error") or "unknown job failure")
                print(f"job failed: {last_error}", file=sys.stderr)
                raise SystemExit(1)

        if not pending_job_ids:
            _print_summary(documents=documents, entities=entities, relations=relations)
            return

        if time.monotonic() - started_at >= timeout_seconds:
            print(
                "timed out waiting for extraction jobs; check whether kb-worker is running",
                file=sys.stderr,
            )
            raise SystemExit(1)
        time.sleep(_POLL_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> None:
    try:
        ns = _parse_args(argv or [])
        config = load_kb_service_config(Path(ns.config).expanduser())
        tenant_id = config.service.tenant_id
        kb_id = str(ns.kb)
        data_dir = config.data_dir()
        database_url = config.queue_database_url()

        _require_known_kb(tenant_id, kb_id, data_dir=data_dir)
        kb_database = _knowledge_database(tenant_id, data_dir=data_dir)
        set_extraction_enabled(tenant_id, kb_id, True, database=kb_database)

        document_rows = list_documents(tenant_id, kb_id, database=kb_database)
        job_ids: list[str] = []
        for row in document_rows:
            job = kb_ingest_jobs.enqueue_job(
                job_type="extraction",
                tenant_id=tenant_id,
                kb_id=kb_id,
                connector_ref={"document_id": str(row["document_id"])},
                database_url=database_url,
            )
            job_ids.append(str(job["id"]))

        if ns.wait:
            _wait_for_jobs(job_ids, database_url=database_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
