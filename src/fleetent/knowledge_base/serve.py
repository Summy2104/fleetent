"""Per-tenant HTTP read service for knowledge base retrieval."""

from __future__ import annotations

import argparse
import os
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from fleetent import kb_ingest_jobs
from fleetent import knowledge_base as kb_runtime
from fleetent.db import SQLiteDatabase, create_database
from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, decode_ingress_principal
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.core.models import KnowledgeChunk
from fleetent.knowledge_base.ingest import runtime as kb_ingest_runtime
from fleetent.knowledge_base.management import runtime as kb_management_runtime
from fleetent.knowledge_base.retrieval import evaluation as retrieval_evaluation
from fleetent.tenant_router import SQLiteTenantBackend, StandaloneKBTenantBackend, TenantRouter


@dataclass(frozen=True)
class KBServeConfig:
    tenant_id: str
    service_key_ref: str
    host: str = "127.0.0.1"
    port: int = 8768
    max_upload_bytes: int = 50 * 1024 * 1024
    default_mode: str = "hybrid"
    data_dir: Path | None = None
    queue_database_url: str = ""
    multi_tenant_root: bool = False


class PrincipalPayload(BaseModel):
    user_id: str
    tenant_id: str


class SearchRequest(BaseModel):
    principal: PrincipalPayload
    query: str
    kb_ids: list[str] = Field(default_factory=list)
    limit: int = 10
    mode: str | None = None
    rerank: bool = False
    use_planner: bool = False


class CreateKnowledgeBaseRequest(BaseModel):
    kb_id: str
    description: str = ""
    extraction_enabled: bool = False


class UpdateKnowledgeBaseRequest(BaseModel):
    description: str | None = None
    extraction_enabled: bool | None = None


class EvaluationRequest(BaseModel):
    kb_id: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb serve")
    parser.add_argument("--tenant", default="", help="tenant id served by this process")
    parser.add_argument("--service-key", default="", help="service key ref: env:VAR or file://path")
    parser.add_argument(
        "--config",
        default="",
        help="standalone kb-service.yaml path; when set, service settings come from this file",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=8768, help="bind port")
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=("vector", "keyword", "hybrid"),
        help="default retrieval mode for /search",
    )
    return parser.parse_args(argv)


def _database() -> SQLiteDatabase:
    from fleetent.config import Settings

    return create_database(Settings().database_url)


def _tenant_router(
    data_dir: Path | None = None, *, multi_tenant_root: bool = False
) -> TenantRouter:
    resolved_data_dir = data_dir or _database().path.parent
    if multi_tenant_root:
        return TenantRouter(SQLiteTenantBackend(data_dir=resolved_data_dir))
    return TenantRouter(StandaloneKBTenantBackend(data_dir=resolved_data_dir))


def _resolve_auth_ref(auth_ref: str) -> str:
    if auth_ref.startswith("env:"):
        env_name = auth_ref.removeprefix("env:")
        value = os.getenv(env_name)
        if value:
            return value
        raise ValueError(f"kb service key env var is missing: {env_name}")
    path = Path(auth_ref.removeprefix("file://")).expanduser()
    return path.read_text(encoding="utf-8")


def _bootstrap_runtime(
    tenant_id: str,
    *,
    data_dir: Path | None = None,
    multi_tenant_root: bool = False,
) -> None:
    if multi_tenant_root:
        router = _tenant_router(data_dir, multi_tenant_root=True)
    elif data_dir is not None:
        router = _tenant_router(data_dir)
    else:
        router = _tenant_router()
    scope = router.tenant_scope(tenant_id)
    kb_runtime.runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
    kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)


def _knowledge_chunk_to_wire_dict(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "tenant_id": chunk.tenant_id,
        "kb_id": chunk.kb_id,
        "filename": chunk.filename,
        "content": chunk.content,
        "position": chunk.position,
        "score": chunk.score,
        "source": chunk.source,
        "source_url": chunk.source_url,
        "metadata": dict(chunk.metadata),
    }


def _management_chunk_to_wire_dict(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.id,
        "document_id": chunk.document_id,
        "kb_id": chunk.kb_id,
        "filename": chunk.filename,
        "content": chunk.content,
        "position": chunk.position,
        "score": chunk.score,
        "source": chunk.source,
        "source_url": chunk.source_url,
        "section": chunk.metadata.get("section_title") or chunk.metadata.get("section_path", ""),
        "section_path": chunk.metadata.get("section_path", ""),
    }


def _datetime_to_wire(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _connector_status_to_wire(status: kb_runtime.ConnectorStatus) -> dict[str, object]:
    return {
        "connector_id": status.connector_id,
        "connector_type": status.connector_type,
        "tenant_id": status.tenant_id,
        "kb_id": status.kb_id,
        "last_status": status.last_status,
        "last_started_at": _datetime_to_wire(status.last_started_at),
        "last_finished_at": _datetime_to_wire(status.last_finished_at),
        "last_summary": status.last_summary,
        "last_error": status.last_error,
    }


def _job_status_to_wire(job: dict[str, object]) -> dict[str, object]:
    return {
        "id": job["id"],
        "job_type": job["job_type"],
        "tenant_id": job["tenant_id"],
        "kb_id": job["kb_id"],
        "status": job["status"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "last_error": job["last_error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "claimed_at": job["claimed_at"],
        "finished_at": job["finished_at"],
        "result": job.get("result"),
    }


def _retrieval_metrics_to_wire(
    metrics: retrieval_evaluation.RetrievalMetrics,
) -> dict[str, object]:
    return {
        "recall_at_k": metrics.recall_at_k,
        "mrr": metrics.mrr,
        "query_count": metrics.query_count,
        "hit_count": metrics.hit_count,
        "hit_rate": metrics.hit_rate,
        "average_hit_rank": metrics.average_hit_rank,
    }


def create_app(config: KBServeConfig):  # type: ignore[no-untyped-def]
    previous_db = kb_runtime.runtime._kb_db
    previous_backend = kb_runtime.runtime._kb_vector_backend
    if config.multi_tenant_root:
        router = _tenant_router(config.data_dir, multi_tenant_root=True)
    elif config.data_dir is not None:
        router = _tenant_router(config.data_dir)
    else:
        router = _tenant_router()
    if config.tenant_id:
        if config.multi_tenant_root:
            _bootstrap_runtime(
                config.tenant_id,
                data_dir=config.data_dir,
                multi_tenant_root=True,
            )
        elif config.data_dir is not None:
            _bootstrap_runtime(config.tenant_id, data_dir=config.data_dir)
        else:
            _bootstrap_runtime(config.tenant_id)
        kb_runtime.runtime.set_database(previous_db)
        kb_runtime.runtime.set_vector_backend(previous_backend)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.tenant_id:
            if config.multi_tenant_root:
                _bootstrap_runtime(
                    config.tenant_id,
                    data_dir=config.data_dir,
                    multi_tenant_root=True,
                )
            elif config.data_dir is not None:
                _bootstrap_runtime(config.tenant_id, data_dir=config.data_dir)
            else:
                _bootstrap_runtime(config.tenant_id)
        yield

    app = FastAPI(title="fleetent kb-read-service", lifespan=lifespan)
    app.state.kb_serve_config = config
    app.state.kb_service_key = _resolve_auth_ref(config.service_key_ref)
    app.state.kb_principal_type = Principal

    def _knowledge_database(tenant_id: str) -> SQLiteDatabase:
        return router.tenant_scope(tenant_id).open_kb_db(KB_MIGRATIONS)

    def _queue_database_url(tenant_id: str) -> str:
        if not config.multi_tenant_root:
            return config.queue_database_url
        tenant_data_dir = config.data_dir or _database().path.parent
        queue_path = tenant_data_dir / "tenants" / tenant_id / "kb" / "data" / "kb_ingest_queue.db"
        return f"sqlite:///{queue_path}"

    @contextmanager
    def _tenant_runtime(tenant_id: str):
        scope = router.tenant_scope(tenant_id)
        previous_db = kb_runtime.runtime._kb_db
        previous_backend = kb_runtime.runtime._kb_vector_backend
        kb_runtime.runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
        kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)
        try:
            yield
        finally:
            kb_runtime.runtime.set_database(previous_db)
            kb_runtime.runtime.set_vector_backend(previous_backend)

    def _require_authorized_principal(
        authorization: str | None,
        principal_header: str | None,
        body_principal: PrincipalPayload | None = None,
    ) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization.removeprefix("Bearer ").strip()
        if token != app.state.kb_service_key:
            raise HTTPException(status_code=401, detail="invalid bearer token")
        try:
            principal = decode_ingress_principal(principal_header)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if principal is None:
            raise HTTPException(status_code=401, detail="missing principal header")
        if body_principal is not None and (
            principal.user_id != body_principal.user_id
            or principal.tenant_id != body_principal.tenant_id
        ):
            raise HTTPException(status_code=403, detail="principal mismatch")
        if config.tenant_id and principal.tenant_id != config.tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        return principal

    def _knowledge_base_row_to_wire(row: dict[str, object]) -> dict[str, object]:
        return {
            "tenant_id": str(row["tenant_id"]),
            "kb_id": str(row["kb_id"]),
            "description": str(row["description"]),
            "doc_count": _row_int(row["doc_count"]),
            "chunk_count": _row_int(row["chunk_count"]),
            "last_import": row["last_import"],
            "archived": bool(row["archived_at"] is not None),
        }

    def _row_int(value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value)
        raise TypeError(f"expected int-like value, got {type(value).__name__}")

    def _current_knowledge_base(tenant_id: str, kb_id: str) -> dict[str, object]:
        for row in kb_management_runtime.list_knowledge_bases(
            tenant_id,
            database=_knowledge_database(tenant_id),
        ):
            data = dict(row)
            if str(data["kb_id"]) == kb_id:
                return data
        raise HTTPException(status_code=404, detail="kb not found")

    def _upload_root(tenant_id: str, kb_id: str) -> Path:
        if config.multi_tenant_root:
            base_dir = (config.data_dir or _database().path.parent) / "tenants" / tenant_id / "kb"
        else:
            base_dir = (config.data_dir or _database().path.parent).parent
        return base_dir / "uploads" / kb_id

    def _sanitize_upload_filename(filename: str) -> str:
        sanitized = filename.replace("\\", "/").split("/")[-1].strip()
        return sanitized or "upload.bin"

    async def _stage_upload(file: UploadFile, *, tenant_id: str, kb_id: str) -> Path:
        upload_dir = _upload_root(tenant_id, kb_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        staged_path = (
            upload_dir / f"{uuid.uuid4()}-{_sanitize_upload_filename(file.filename or '')}"
        )
        seen = 0
        try:
            with staged_path.open("wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        return staged_path
                    seen += len(chunk)
                    if seen > config.max_upload_bytes:
                        raise HTTPException(
                            status_code=413, detail="upload exceeds max_upload_bytes"
                        )
                    handle.write(chunk)
        except Exception:
            staged_path.unlink(missing_ok=True)
            raise

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "tenant_id": config.tenant_id}

    @app.get("/kb")
    def list_knowledge_bases(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> list[dict[str, object]]:
        principal = _require_authorized_principal(authorization, principal_header)
        rows = kb_management_runtime.list_knowledge_bases(
            principal.tenant_id,
            database=_knowledge_database(principal.tenant_id),
        )
        return [_knowledge_base_row_to_wire(dict(row)) for row in rows]

    @app.post("/kb")
    def create_knowledge_base(
        request: Annotated[CreateKnowledgeBaseRequest, Body(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        kb_management_runtime.create_knowledge_base(
            principal.tenant_id,
            request.kb_id,
            request.description,
            extraction_enabled=request.extraction_enabled,
            database=_knowledge_database(principal.tenant_id),
        )
        row = _current_knowledge_base(principal.tenant_id, request.kb_id)
        return {
            "kb_id": str(row["kb_id"]),
            "tenant_id": str(row["tenant_id"]),
            "description": str(row["description"]),
            "extraction_enabled": bool(_row_int(row["extraction_enabled"])),
        }

    @app.patch("/kb/{kb_id}")
    def update_knowledge_base(
        kb_id: str,
        request: Annotated[UpdateKnowledgeBaseRequest, Body(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        if request.description is not None:
            updated = kb_management_runtime.update_knowledge_base_description(
                principal.tenant_id,
                kb_id,
                request.description,
                database=_knowledge_database(principal.tenant_id),
            )
            if not updated:
                raise HTTPException(status_code=404, detail="kb not found")
        if request.extraction_enabled is not None:
            updated = kb_management_runtime.set_extraction_enabled(
                principal.tenant_id,
                kb_id,
                request.extraction_enabled,
                database=_knowledge_database(principal.tenant_id),
            )
            if not updated:
                raise HTTPException(status_code=404, detail="kb not found")
        row = _current_knowledge_base(principal.tenant_id, kb_id)
        return {
            "kb_id": str(row["kb_id"]),
            "description": str(row["description"]),
            "extraction_enabled": bool(_row_int(row["extraction_enabled"])),
        }

    @app.delete("/kb/{kb_id}")
    async def archive_knowledge_base(
        kb_id: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        archived = await kb_management_runtime.archive_knowledge_base(
            principal.tenant_id,
            kb_id,
            database=_knowledge_database(principal.tenant_id),
        )
        if not archived:
            raise HTTPException(status_code=404, detail="kb not found or already archived")
        return {"kb_id": kb_id, "archived": True}

    @app.get("/kb/{kb_id}/documents")
    def list_documents(
        kb_id: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> list[dict[str, object]]:
        principal = _require_authorized_principal(authorization, principal_header)
        rows = kb_management_runtime.list_documents(
            principal.tenant_id,
            kb_id,
            database=_knowledge_database(principal.tenant_id),
        )
        return [
            {
                "document_id": str(row["document_id"]),
                "filename": str(row["filename"]),
                "source": str(row["source"]),
                "source_url": row["source_url"],
                "chunks": int(row["chunks"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @app.post("/kb/{kb_id}/documents")
    async def upload_document(
        kb_id: str,
        file: Annotated[UploadFile, File(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        _current_knowledge_base(principal.tenant_id, kb_id)
        staged_path = await _stage_upload(file, tenant_id=principal.tenant_id, kb_id=kb_id)
        job = kb_ingest_jobs.enqueue_job(
            job_type="sync_directory",
            tenant_id=principal.tenant_id,
            kb_id=kb_id,
            connector_ref={"path": str(staged_path)},
            database_url=_queue_database_url(principal.tenant_id),
        )
        return {"job_id": str(job["id"])}

    @app.get("/kb/{kb_id}/documents/{document_id}/chunks")
    def preview_document_chunks(
        kb_id: str,
        document_id: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> list[dict[str, object]]:
        principal = _require_authorized_principal(authorization, principal_header)
        chunks = kb_management_runtime.preview_document_chunks(
            principal.tenant_id,
            kb_id,
            document_id,
            database=_knowledge_database(principal.tenant_id),
        )
        return [_management_chunk_to_wire_dict(chunk) for chunk in chunks]

    @app.delete("/kb/{kb_id}/documents/{document_id}")
    async def delete_document(
        kb_id: str,
        document_id: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        deleted = await kb_ingest_runtime.delete_document(
            principal.tenant_id,
            kb_id,
            document_id,
            database=_knowledge_database(principal.tenant_id),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="document not found in kb")
        return {"kb_id": kb_id, "document_id": document_id, "deleted": True}

    @app.post("/evaluations")
    async def run_evaluation(
        request: Annotated[EvaluationRequest, Body(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        _require_authorized_principal(authorization, principal_header)
        result = await retrieval_evaluation.run_deterministic_fixture_suite()
        return {
            "kb_id": request.kb_id,
            "metrics": _retrieval_metrics_to_wire(result.metrics),
            "hit_ranking": list(result.hit_ranking),
            "fixtures": [
                {
                    "name": fixture.fixture_name,
                    "document_count": fixture.document_count,
                    "metrics": _retrieval_metrics_to_wire(fixture.metrics),
                    "queries": [
                        {
                            "query": query_result.query,
                            "recall_at_k": query_result.recall_at_k,
                            "forbidden_hits": list(query_result.forbidden_hits),
                            "ranked_hit": (
                                {
                                    "rank": query_result.ranked_hit.rank,
                                    "reciprocal_rank": query_result.ranked_hit.reciprocal_rank,
                                    "matched_snippets": list(
                                        query_result.ranked_hit.matched_snippets
                                    ),
                                }
                                if query_result.ranked_hit is not None
                                else None
                            ),
                        }
                        for query_result in fixture.query_results
                    ],
                }
                for fixture in result.fixtures
            ],
        }

    @app.get("/status")
    def status(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, object]:
        principal = _require_authorized_principal(authorization, principal_header)
        with _tenant_runtime(principal.tenant_id):
            connector_rows = kb_runtime.operations.list_connector_statuses(principal.tenant_id)
        job_rows = kb_ingest_jobs.list_jobs(
            tenant_id=principal.tenant_id,
            database_url=_queue_database_url(principal.tenant_id),
        )
        return {
            "tenant_id": principal.tenant_id,
            "connectors": [_connector_status_to_wire(row) for row in connector_rows],
            "jobs": [_job_status_to_wire(row) for row in job_rows],
        }

    @app.post("/search")
    async def search_chunks(
        request: Annotated[SearchRequest, Body(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, list[dict[str, object]]]:
        principal = _require_authorized_principal(
            authorization, principal_header, request.principal
        )
        mode = request.mode or config.default_mode
        if request.rerank and mode != "hybrid":
            raise ValueError("rerank only supports hybrid knowledge search mode")
        with _tenant_runtime(principal.tenant_id):
            if request.use_planner:
                plan = kb_runtime.plan_knowledge_search(
                    request.query,
                    kb_runtime.KnowledgeSearchOptions(
                        tenant_id=principal.tenant_id,
                        kb_ids=request.kb_ids,
                        limit=request.limit,
                        rerank=request.rerank,
                    ),
                )
                chunks = await kb_runtime.execute_knowledge_search_plan(plan)
            else:
                chunks = await kb_runtime.search(
                    query=request.query,
                    tenant_id=principal.tenant_id,
                    kb_ids=request.kb_ids,
                    limit=request.limit,
                    mode=mode,
                    rerank=request.rerank,
                )
        return {"chunks": [_knowledge_chunk_to_wire_dict(chunk) for chunk in chunks]}

    return app


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        import sys

        argv = sys.argv[1:]
    ns = _parse_args(argv)
    if ns.config:
        from pydantic import ValidationError

        from fleetent.knowledge_base.service_config import (
            load_host_service_config,
            load_kb_service_config,
            validate_kb_service_boot,
        )

        os.environ["FLEETENT_KB_SERVICE_CONFIG"] = str(Path(ns.config).expanduser())
        config_path = Path(ns.config).expanduser()
        try:
            host_config = load_host_service_config(config_path)
        except ValidationError:
            standalone_config = load_kb_service_config(config_path)
            validate_kb_service_boot(standalone_config)
            standalone_config.configure_process_runtime()
            config = KBServeConfig(
                tenant_id=standalone_config.service.tenant_id,
                service_key_ref=standalone_config.service.service_key_ref,
                host=standalone_config.service.host,
                port=standalone_config.service.port,
                default_mode=standalone_config.retrieval.default_mode,
                data_dir=standalone_config.data_dir(),
                queue_database_url=standalone_config.queue_database_url(),
            )
        else:
            host_config.configure_process_runtime()
            config = KBServeConfig(
                tenant_id=ns.tenant,
                service_key_ref=host_config.service.service_key_ref,
                host=host_config.service.host,
                port=host_config.service.port,
                default_mode=host_config.retrieval.default_mode,
                data_dir=config_path.parent,
                multi_tenant_root=True,
            )
    else:
        if not ns.tenant or not ns.service_key:
            raise SystemExit("--tenant and --service-key are required when --config is not set")
        config = KBServeConfig(
            tenant_id=ns.tenant,
            service_key_ref=ns.service_key,
            host=ns.host,
            port=ns.port,
            default_mode=ns.mode,
        )
    from fleetent.logging_setup import setup_process_logging

    setup_process_logging(log_format=os.getenv("LOG_FORMAT", "console"))
    app = create_app(config)
    from uvicorn import run as uvicorn_run

    uvicorn_run(app, host=config.host, port=config.port, log_level="info")
