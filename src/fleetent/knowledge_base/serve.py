"""Per-tenant HTTP read service for knowledge base retrieval."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from fleetent import knowledge_base as kb_runtime
from fleetent.db import SQLiteDatabase, create_database
from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, decode_ingress_principal
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.core.models import KnowledgeChunk
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


@dataclass(frozen=True)
class KBServeConfig:
    tenant_id: str
    service_key_ref: str
    host: str = "127.0.0.1"
    port: int = 8787
    default_mode: str = "hybrid"


class PrincipalPayload(BaseModel):
    user_id: str
    tenant_id: str


class SearchRequest(BaseModel):
    principal: PrincipalPayload
    query: str
    kb_ids: list[str] = Field(default_factory=list)
    limit: int = 10


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb-serve")
    parser.add_argument("--tenant", required=True, help="tenant id served by this process")
    parser.add_argument(
        "--service-key", required=True, help="service key ref: env:VAR or file://path"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=8787, help="bind port")
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


def _tenant_router() -> TenantRouter:
    data_dir = _database().path.parent
    return TenantRouter(SQLiteTenantBackend(data_dir=data_dir))


def _resolve_auth_ref(auth_ref: str) -> str:
    if auth_ref.startswith("env:"):
        env_name = auth_ref.removeprefix("env:")
        value = os.getenv(env_name)
        if value:
            return value
        raise ValueError(f"kb service key env var is missing: {env_name}")
    path = Path(auth_ref.removeprefix("file://")).expanduser()
    return path.read_text(encoding="utf-8")


def _bootstrap_runtime(tenant_id: str) -> None:
    scope = _tenant_router().tenant_scope(tenant_id)
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


def create_app(config: KBServeConfig):  # type: ignore[no-untyped-def]
    _bootstrap_runtime(config.tenant_id)
    app = FastAPI(title="fleetent kb-read-service")
    app.state.kb_serve_config = config
    app.state.kb_service_key = _resolve_auth_ref(config.service_key_ref)
    app.state.kb_principal_type = Principal

    def _require_authorized_principal(
        authorization: str | None,
        principal_header: str | None,
        body_principal: PrincipalPayload,
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
        if (
            principal.user_id != body_principal.user_id
            or principal.tenant_id != body_principal.tenant_id
        ):
            raise HTTPException(status_code=403, detail="principal mismatch")
        if principal.tenant_id != config.tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        return principal

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "tenant_id": config.tenant_id}

    @app.post("/search")
    async def search_chunks(
        request: Annotated[SearchRequest, Body(...)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        principal_header: Annotated[str | None, Header(alias=INGRESS_PRINCIPAL_HEADER)] = None,
    ) -> dict[str, list[dict[str, object]]]:
        _require_authorized_principal(authorization, principal_header, request.principal)
        chunks = await kb_runtime.search(
            query=request.query,
            tenant_id=config.tenant_id,
            kb_ids=request.kb_ids,
            limit=request.limit,
            mode=config.default_mode,
            rerank=False,
        )
        return {"chunks": [_knowledge_chunk_to_wire_dict(chunk) for chunk in chunks]}

    return app


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        import sys

        argv = sys.argv[1:]
    ns = _parse_args(argv)
    config = KBServeConfig(
        tenant_id=ns.tenant,
        service_key_ref=ns.service_key,
        host=ns.host,
        port=ns.port,
        default_mode=ns.mode,
    )
    app = create_app(config)
    from uvicorn import run as uvicorn_run

    uvicorn_run(app, host=config.host, port=config.port)
