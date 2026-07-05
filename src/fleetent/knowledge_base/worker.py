"""KB ingest worker entrypoint and queue consumer."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleetent import kb_ingest_jobs, vector_store
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
from fleetent.tenant_router import SQLiteTenantBackend, StandaloneKBTenantBackend, TenantRouter

if False:  # pragma: no cover
    from fleetent.knowledge_base.service_config import KBHostServiceConfig, KBServiceConfig


@dataclass(frozen=True)
class KBWorkerConfig:
    queue_database_url: str = ""
    substrate_database_url: str = ""
    vault_addr: str = ""
    vault_token: str = ""
    home_dir: Path = Path()


def load_config() -> KBWorkerConfig:
    """Load legacy kb-worker config from process env."""
    home_dir = Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()
    return KBWorkerConfig(
        queue_database_url=os.environ.get("FLEETENT_KB_WORKER_QUEUE_DATABASE_URL", "").strip(),
        substrate_database_url=os.environ.get(
            "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL", ""
        ).strip(),
        vault_addr=os.environ.get("FLEETENT_KB_WORKER_VAULT_ADDR", "").strip(),
        vault_token=os.environ.get("FLEETENT_KB_WORKER_VAULT_TOKEN", "").strip(),
        home_dir=home_dir,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb worker")
    parser.add_argument(
        "--config",
        default="",
        help="standalone kb-service.yaml path; when set, queue/data paths come from this file",
    )
    parser.add_argument("--tenant", default="", help="lock worker to one tenant")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="seconds to sleep when no ingest job is available",
    )
    return parser.parse_args(argv)


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _tenant_router(
    data_dir: Path | None = None, *, multi_tenant_root: bool = False
) -> TenantRouter:
    resolved_data_dir = data_dir or _database().path.parent
    if multi_tenant_root:
        return TenantRouter(SQLiteTenantBackend(data_dir=resolved_data_dir))
    return TenantRouter(StandaloneKBTenantBackend(data_dir=resolved_data_dir))


def _knowledge_database(
    tenant_id: str,
    *,
    data_dir: Path | None = None,
    migrations: list[tuple[int, str]] | None = None,
    multi_tenant_root: bool = False,
) -> SQLiteDatabase:
    return (
        _tenant_router(data_dir, multi_tenant_root=multi_tenant_root)
        .tenant_scope(tenant_id)
        .open_kb_db(migrations or KB_MIGRATIONS)
    )


def _require_queue_database_url(queue_database_url: str | None) -> str:
    if not queue_database_url:
        raise ValueError("queue database_url is required")
    return queue_database_url


@contextmanager
def _use_kb_runtime(
    tenant_id: str,
    *,
    data_dir: Path | None = None,
    queue_database_url: str | None = None,
    multi_tenant_root: bool = False,
) -> Iterator[None]:
    scope = _tenant_router(data_dir, multi_tenant_root=multi_tenant_root).tenant_scope(tenant_id)
    previous_db = kb_runtime.runtime._kb_db
    previous_backend = kb_runtime.runtime._kb_vector_backend
    previous_queue_database_url = kb_runtime.runtime._kb_queue_database_url
    kb_runtime.runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
    kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)
    kb_runtime.runtime.set_queue_database_url(queue_database_url)
    try:
        yield
    finally:
        kb_runtime.runtime.set_database(previous_db)
        kb_runtime.runtime.set_vector_backend(previous_backend)
        kb_runtime.runtime.set_queue_database_url(previous_queue_database_url)


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


def _require_active_kb(
    tenant_id: str,
    kb_id: str,
    *,
    data_dir: Path | None = None,
    multi_tenant_root: bool = False,
) -> None:
    if not _kb_is_active_knowledge_base(
        tenant_id,
        kb_id,
        database=_knowledge_database(
            tenant_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root
        ),
    ):
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


def run_job(
    job: dict[str, Any],
    *,
    data_dir: Path | None = None,
    queue_database_url: str | None = None,
    multi_tenant_root: bool = False,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    payload = kb_ingest_jobs.get_job_payload(job)
    job_type = str(job["job_type"])
    tenant_id = str(job["tenant_id"])
    kb_id = str(job["kb_id"])

    if job_type == "import_document":
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root)
        parsed = _parse_import_document(
            str(payload["source"]),
            str(payload["content"]),
            str(payload["document_format"]),
        )
        with _use_kb_runtime(
            tenant_id,
            data_dir=data_dir,
            queue_database_url=queue_database_url,
            multi_tenant_root=multi_tenant_root,
        ):
            document = asyncio.run(
                ingest_parsed(
                    parsed,
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    source=str(payload["source"]),
                    source_url=None,
                    settings=_ingest_settings(job),
                    database=_knowledge_database(
                        tenant_id,
                        data_dir=data_dir,
                        multi_tenant_root=multi_tenant_root,
                    ),
                )
            )
        chunks = KnowledgeStore(
            _knowledge_database(tenant_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root)
        ).get_document_chunks(document.id)
        return {
            "document_id": document.id,
            "chunks": len(chunks),
            "filename": document.filename,
            "source": document.source,
            "source_url": document.source_url,
            "wired": True,
        }

    if job_type == "sync_directory":
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root)
        config = LocalDirectorySourceConfig(
            source_id=f"admin-local:{tenant_id}:{kb_id}:{Path(str(payload['path'])).expanduser().resolve()}",
            root_path=str(payload["path"]),
            allowed_roots=[str(payload["path"])],
        )
        with _use_kb_runtime(
            tenant_id,
            data_dir=data_dir,
            queue_database_url=queue_database_url,
            multi_tenant_root=multi_tenant_root,
        ):
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
        connector_env: Mapping[str, str] | None = None
        if home_dir is not None:
            from fleetent.knowledge_base.service_config import load_tenant_connectors

            _, connector_env = load_tenant_connectors(home_dir, tenant_id)
        with _use_kb_runtime(
            tenant_id,
            data_dir=data_dir,
            queue_database_url=queue_database_url,
            multi_tenant_root=multi_tenant_root,
        ):
            connector_result = asyncio.run(
                knowledge_base.run_connector_sync(
                    connector_id,
                    settings=_connector_settings(job, payload),
                    dry_run=False,
                    env=connector_env,
                )
            )
        return {
            "connector_id": connector_result.connector_id,
            "status": connector_result.status,
            "summary": connector_result.summary,
            "error": connector_result.error,
        }

    if job_type == "extraction":
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root)
        with _use_kb_runtime(
            tenant_id,
            data_dir=data_dir,
            queue_database_url=queue_database_url,
            multi_tenant_root=multi_tenant_root,
        ):
            extraction_summary = asyncio.run(
                kb_runtime.run_entity_extraction(
                    tenant_id,
                    kb_id,
                    document_id=str(payload["document_id"]),
                    extractor="model_policy",
                )
            )
        return {
            "document_id": extraction_summary.document_id,
            "status": extraction_summary.status,
            "documents_scanned": extraction_summary.documents_scanned,
            "chunks_scanned": extraction_summary.chunks_scanned,
            "entities_upserted": extraction_summary.entities_upserted,
            "mentions_written": extraction_summary.mentions_written,
            "relations_written": extraction_summary.relations_written,
            "failed_count": extraction_summary.failed_count,
            "error_summary": extraction_summary.error_summary,
        }

    if job_type == "reindex":
        _require_active_kb(tenant_id, kb_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root)
        with _use_kb_runtime(
            tenant_id,
            data_dir=data_dir,
            queue_database_url=queue_database_url,
            multi_tenant_root=multi_tenant_root,
        ):
            reindex_summary = vector_store.reindex(
                vector_store.ReindexRequest(
                    owner="knowledge_base",
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                )
            )
            if not reindex_summary.dry_run and reindex_summary.failed == 0:
                # Reindex is the sanctioned embedding-model migration path: move the
                # KB's recorded identity to the rebuilt vectors' identity, or the
                # retrieval mismatch guard stays locked after a model switch. A
                # partial rebuild (failed > 0) keeps the old identity — flipping it
                # would bless a namespace that still mixes embedding spaces.
                current = vector_store.current_embedding_identity()
                KnowledgeStore(
                    _knowledge_database(
                        tenant_id, data_dir=data_dir, multi_tenant_root=multi_tenant_root
                    )
                ).set_embedding_identity(tenant_id, kb_id, current.model, current.dimensions)
        return {
            "owner": reindex_summary.owner,
            "namespace": reindex_summary.namespace,
            "dry_run": reindex_summary.dry_run,
            "scanned": reindex_summary.scanned,
            "reindexed": reindex_summary.reindexed,
            "skipped": reindex_summary.skipped,
            "failed": reindex_summary.failed,
        }

    raise ValueError(f"unknown kb ingest job type: {job_type}")


def _tenant_queue_database_url(home_dir: Path, tenant_id: str) -> str:
    return f"sqlite:///{home_dir / 'tenants' / tenant_id / 'kb' / 'data' / 'kb_ingest_queue.db'}"


def _claim_next_multi_tenant_job(
    *,
    home_dir: Path,
    tenant_id: str = "",
) -> tuple[dict[str, Any], str] | None:
    from fleetent.knowledge_base.service_config import discover_tenants

    tenant_ids = [tenant_id] if tenant_id else discover_tenants(home_dir)
    for current_tenant_id in tenant_ids:
        queue_database_url = _tenant_queue_database_url(home_dir, current_tenant_id)
        job = kb_ingest_jobs.claim_next_job(database_url=queue_database_url)
        if job is not None:
            return job, queue_database_url
    return None


def run_once(
    *,
    queue_database_url: str | None = None,
    data_dir: Path | None = None,
    home_dir: Path | None = None,
    tenant_id: str = "",
) -> dict[str, Any] | None:
    multi_tenant_root = home_dir is not None
    if multi_tenant_root:
        claimed = _claim_next_multi_tenant_job(home_dir=home_dir, tenant_id=tenant_id)
        if claimed is None:
            return None
        job, resolved_queue_database_url = claimed
        resolved_data_dir = home_dir
    else:
        resolved_queue_database_url = _require_queue_database_url(queue_database_url)
        job = kb_ingest_jobs.claim_next_job(database_url=resolved_queue_database_url)
        if job is None:
            return None
        resolved_data_dir = data_dir
    try:
        result = run_job(
            job,
            data_dir=resolved_data_dir,
            queue_database_url=resolved_queue_database_url,
            multi_tenant_root=multi_tenant_root,
            home_dir=home_dir,
        )
    except Exception as exc:
        failed = kb_ingest_jobs.mark_failed(
            str(job["id"]),
            str(exc),
            database_url=resolved_queue_database_url,
        )
        if failed is None:
            return {"job_id": str(job["id"]), "status": "missing"}
        return {"job_id": str(job["id"]), "status": str(failed["status"])}
    kb_ingest_jobs.mark_done(
        str(job["id"]), result=result, database_url=resolved_queue_database_url
    )
    return {"job_id": str(job["id"]), "status": "done"}


def run(
    *,
    poll_interval: float,
    queue_database_url: str | None = None,
    data_dir: Path | None = None,
    home_dir: Path | None = None,
    tenant_id: str = "",
    standalone_config: KBServiceConfig | None = None,
    host_config: KBHostServiceConfig | None = None,
) -> None:
    while True:
        if standalone_config is not None:
            from fleetent.knowledge_base.standalone_sweep import sweep

            sweep(standalone_config, queue_database_url=queue_database_url)
        run_once_kwargs: dict[str, object] = {
            "queue_database_url": queue_database_url,
            "data_dir": data_dir,
        }
        if home_dir is not None:
            run_once_kwargs["home_dir"] = home_dir
        if tenant_id:
            run_once_kwargs["tenant_id"] = tenant_id
        processed = run_once(**run_once_kwargs)
        if processed is None:
            time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> None:
    config = load_config()
    ns = _parse_args(argv or [])
    queue_database_url = config.queue_database_url or None
    data_dir: Path | None = None
    standalone_config = None
    host_config = None
    home_dir: Path | None = None
    if ns.config:
        from pydantic import ValidationError

        from fleetent.knowledge_base.service_config import (
            load_host_service_config,
            load_kb_service_config,
            validate_kb_service_boot,
        )

        config_path = Path(ns.config).expanduser()
        try:
            host_config = load_host_service_config(config_path)
        except ValidationError:
            standalone_config = load_kb_service_config(config_path)
            validate_kb_service_boot(standalone_config)
            standalone_config.configure_process_runtime()
            queue_database_url = standalone_config.queue_database_url()
            data_dir = standalone_config.data_dir()
        else:
            host_config.configure_process_runtime()
            home_dir = config_path.parent
    from fleetent.logging_setup import setup_process_logging

    setup_process_logging(log_format=os.getenv("LOG_FORMAT", "console"))
    from fleetent.build_info import log_service_startup

    log_service_startup("kb-worker")
    run_kwargs: dict[str, object] = {
        "poll_interval": ns.poll_interval,
        "queue_database_url": queue_database_url,
        "data_dir": data_dir,
        "standalone_config": standalone_config,
    }
    if home_dir is not None:
        run_kwargs["home_dir"] = home_dir
    if ns.tenant:
        run_kwargs["tenant_id"] = ns.tenant
    if host_config is not None:
        run_kwargs["host_config"] = host_config
    run(**run_kwargs)
