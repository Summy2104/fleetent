from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fleetent import kb_ingest_jobs
from fleetent.knowledge_base.service_config import load_kb_service_config
from fleetent.knowledge_base.worker import _require_active_kb

_POLL_INTERVAL_SECONDS = 0.25
_WAIT_TIMEOUT_SECONDS = 30.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb reindex")
    parser.add_argument("--config", required=True, help="standalone kb-service.yaml path")
    parser.add_argument("--kb", required=True, help="target knowledge base id")
    parser.add_argument("--wait", action="store_true", help="wait for the queued job to finish")
    return parser.parse_args(argv)


def _require_known_kb(tenant_id: str, kb_id: str, *, data_dir: Path) -> None:
    try:
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir)
    except ValueError as exc:
        raise ValueError(
            f"KB {kb_id!r} does not exist for tenant {tenant_id!r}. "
            "Create it first via `fleetent kb create --config <kb-service.yaml> --kb <kb_id>`."
        ) from exc


def _print_summary(job: dict[str, object]) -> None:
    result = kb_ingest_jobs.get_job_result(job) or {}
    print(
        " ".join(
            [
                f"scanned={int(result.get('scanned', 0))}",
                f"reindexed={int(result.get('reindexed', 0))}",
                f"skipped={int(result.get('skipped', 0))}",
                f"failed={int(result.get('failed', 0))}",
            ]
        )
    )


def _wait_for_job(
    job_id: str,
    *,
    database_url: str,
    timeout_seconds: float = _WAIT_TIMEOUT_SECONDS,
) -> None:
    started_at = time.monotonic()
    while True:
        job = kb_ingest_jobs.get_job(job_id, database_url=database_url)
        if job is None:
            print(f"job {job_id} disappeared from queue", file=sys.stderr)
            raise SystemExit(1)

        status = str(job["status"])
        if status == "done":
            _print_summary(job)
            return
        if status == "failed":
            _print_summary(job)
            last_error = str(job.get("last_error") or "unknown job failure")
            print(f"job failed: {last_error}", file=sys.stderr)
            raise SystemExit(1)

        if time.monotonic() - started_at >= timeout_seconds:
            print(
                f"timed out waiting for reindex job {job_id}; check whether kb-worker is running",
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
        job = kb_ingest_jobs.enqueue_job(
            job_type="reindex",
            tenant_id=tenant_id,
            kb_id=kb_id,
            connector_ref={},
            database_url=database_url,
        )
        if ns.wait:
            _wait_for_job(str(job["id"]), database_url=database_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
