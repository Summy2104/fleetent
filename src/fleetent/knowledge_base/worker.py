"""KB ingest worker entrypoint and queue consumer."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleetent import kb_ingest_jobs
from fleetent import knowledge_base as kb_runtime
from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base import operations as knowledge_base
from fleetent.knowledge_base import parsers as legacy_parsers
from fleetent.knowledge_base.core import KnowledgeStore
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.ingest.config import as_knowledge_base_settings
from fleetent.knowledge_base.ingest.connectors.sync import (
    LocalDirectorySourceConfig,
    sync_local_directory,
)
from fleetent.knowledge_base.ingest.runtime import ingest_parsed
from fleetent.knowledge_base.management.runtime import (
    is_active_knowledge_base as _kb_is_active_knowledge_base,
)
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


@dataclass(frozen=True)
class KBWorkerConfig:
    queue_database_url: str = ""
    substrate_database_url: str = ""
    embedding_backend: str = ""
    embedding_endpoint: str = ""
    embedding_model: str = ""
    vault_addr: str = ""
    vault_token: str = ""
    home_dir: Path = Path()


def load_config() -> KBWorkerConfig:
    """Load kb-worker config from process env plus ``$FLEETENT_HOME/kb-worker/.env``."""
    home_dir = Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()
    env_path = home_dir / "kb-worker" / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    return KBWorkerConfig(
        queue_database_url=os.environ.get("FLEETENT_KB_WORKER_QUEUE_DATABASE_URL", "").strip(),
        substrate_database_url=os.environ.get(
            "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL", ""
        ).strip(),
        embedding_backend=os.environ.get("FLEETENT_KB_WORKER_EMBEDDING_BACKEND", "").strip(),
        embedding_endpoint=os.environ.get("FLEETENT_KB_WORKER_EMBEDDING_ENDPOINT", "").strip(),
        embedding_model=os.environ.get("FLEETENT_KB_WORKER_EMBEDDING_MODEL", "").strip(),
        vault_addr=os.environ.get("FLEETENT_KB_WORKER_VAULT_ADDR", "").strip(),
        vault_token=os.environ.get("FLEETENT_KB_WORKER_VAULT_TOKEN", "").strip(),
        home_dir=home_dir,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb-worker")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="seconds to sleep when no ingest job is available",
    )
    return parser.parse_args(argv)


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _tenant_router() -> TenantRouter:
    data_dir = _database().path.parent
    return TenantRouter(SQLiteTenantBackend(data_dir=data_dir))


def _knowledge_database(tenant_id: str) -> SQLiteDatabase:
    return _tenant_router().tenant_scope(tenant_id).open_kb_db(KB_MIGRATIONS)


@contextmanager
def _use_kb_runtime(tenant_id: str) -> Iterator[None]:
    scope = _tenant_router().tenant_scope(tenant_id)
    previous_db = kb_runtime.runtime._kb_db
    previous_backend = kb_runtime.runtime._kb_vector_backend
    kb_runtime.runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
    kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)
    try:
        yield
    finally:
        kb_runtime.runtime.set_database(previous_db)
        kb_runtime.runtime.set_vector_backend(previous_backend)


def _parse_import_document(
    source: str, content: str, document_format: str
) -> legacy_parsers.ParsedDocument:
    normalized_format = document_format.lower()
    if normalized_format in {"text", "txt"}:
        return legacy_parsers.parse_text(source, content)
    if normalized_format in {"markdown", "md"}:
        return legacy_parsers.parse_markdown(source, content)
    if normalized_format in {"html", "htm"}:
        return legacy_parsers.parse_html(source, content)
    raise ValueError(f"unsupported document_format: {document_format}")


def _require_active_kb(tenant_id: str, kb_id: str) -> None:
    if not _kb_is_active_knowledge_base(tenant_id, kb_id, database=_knowledge_database(tenant_id)):
        raise ValueError("kb not found or archived")


def _ingest_settings(job: dict[str, Any]) -> KnowledgeBaseSettings:
    return as_knowledge_base_settings(
        default_tenant_id=str(job["tenant_id"]),
        default_kb_id=str(job["kb_id"]),
    )


def _connector_settings(job: dict[str, Any], payload: dict[str, Any]) -> KnowledgeBaseSettings:
    config = dict(payload.get("config") or {})
    cred_ref = str(job.get("cred_ref") or "")
    if cred_ref:
        config["credential_ref"] = cred_ref
    connector_row = {
        "connector_id": payload["connector_id"],
        "kind": payload["kind"],
        "tenant_id": str(job["tenant_id"]),
        "kb_id": str(job["kb_id"]),
        "enabled": True,
        "config": config,
    }
    return as_knowledge_base_settings(
        connectors=[connector_row],
        default_tenant_id=str(job["tenant_id"]),
        default_kb_id=str(job["kb_id"]),
    )


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = kb_ingest_jobs.get_job_payload(job)
    job_type = str(job["job_type"])
    tenant_id = str(job["tenant_id"])
    kb_id = str(job["kb_id"])

    if job_type == "import_document":
        _require_active_kb(tenant_id, kb_id)
        parsed = _parse_import_document(
            str(payload["source"]),
            str(payload["content"]),
            str(payload["document_format"]),
        )
        with _use_kb_runtime(tenant_id):
            document = asyncio.run(
                ingest_parsed(
                    parsed,
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    source=str(payload["source"]),
                    source_url=None,
                    settings=_ingest_settings(job),
                    database=_knowledge_database(tenant_id),
                )
            )
        chunks = KnowledgeStore(_knowledge_database(tenant_id)).get_document_chunks(document.id)
        return {
            "document_id": document.id,
            "chunks": len(chunks),
            "filename": document.filename,
            "source": document.source,
            "source_url": document.source_url,
            "wired": True,
        }

    if job_type == "sync_directory":
        _require_active_kb(tenant_id, kb_id)
        config = LocalDirectorySourceConfig(
            source_id=f"admin-local:{tenant_id}:{kb_id}:{Path(str(payload['path'])).expanduser().resolve()}",
            root_path=str(payload["path"]),
            allowed_roots=[str(payload["path"])],
        )
        with _use_kb_runtime(tenant_id):
            summary = asyncio.run(sync_local_directory(config, tenant_id=tenant_id, kb_id=kb_id))
        return {
            "scanned": summary.scanned,
            "ingested": summary.ingested,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "unsupported": summary.unsupported,
            "unchanged": summary.unchanged,
            "deleted": summary.deleted,
            "archived": getattr(summary, "archived", 0),
            "changed": getattr(summary, "changed", 0),
            "auth_failed": getattr(summary, "auth_failed", 0),
            "wired": True,
        }

    if job_type == "connector_sync":
        connector_id = str(payload["connector_id"])
        result = asyncio.run(
            knowledge_base.run_connector_sync(
                connector_id,
                settings=_connector_settings(job, payload),
                dry_run=False,
            )
        )
        return {
            "connector_id": result.connector_id,
            "status": result.status,
            "summary": result.summary,
            "error": result.error,
        }

    raise ValueError(f"unknown kb ingest job type: {job_type}")


def run_once() -> dict[str, Any] | None:
    job = kb_ingest_jobs.claim_next_job()
    if job is None:
        return None
    try:
        result = run_job(job)
    except Exception as exc:
        failed = kb_ingest_jobs.mark_failed(str(job["id"]), str(exc))
        if failed is None:
            return {"job_id": str(job["id"]), "status": "missing"}
        return {"job_id": str(job["id"]), "status": str(failed["status"])}
    kb_ingest_jobs.mark_done(str(job["id"]), result=result)
    return {"job_id": str(job["id"]), "status": "done"}


def run(*, poll_interval: float) -> None:
    while True:
        processed = run_once()
        if processed is None:
            time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> None:
    load_config()
    ns = _parse_args(argv or [])
    from fleetent.build_info import log_service_startup

    log_service_startup("kb-worker")
    run(poll_interval=ns.poll_interval)
