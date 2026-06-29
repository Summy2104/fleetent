"""FastAPI router for /admin/kb — the knowledge-base management face.

Owns the management behaviour only: KB listing/create/edit/archive with binding
protection, document list / chunk preview / single-document delete, the retrieval
test playground, the KB↔Agent binding matrix, the evaluation entry, and the per-KB
observation view.

Parsing / chunking / indexing / vector·keyword·hybrid retrieval / tenant-isolated
recall live in the knowledge-base engine; recall injection + token budget live in
long-term-ctx; per-kb aggregation lives in observability. Those are reached through
injectable seams (mockable in tests). Only the agent_kbs binding is persisted here.
This router never imports the agent loop, so it is testable in isolation.

Auth mirrors user_admin_api: reads allow viewer+admin, writes require admin.
"""

import asyncio
from contextlib import contextmanager
from typing import Any, cast

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent import knowledge_base as kb_runtime
from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeStore
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.ingest.runtime import delete_document as _kb_delete_document
from fleetent.knowledge_base.management.runtime import (
    archive_knowledge_base as _kb_archive_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    create_knowledge_base as _kb_create_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    is_active_knowledge_base as _kb_is_active_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    list_documents as _kb_list_documents,
)
from fleetent.knowledge_base.management.runtime import (
    list_knowledge_bases as _kb_list_knowledge_bases,
)
from fleetent.knowledge_base.management.runtime import (
    preview_document_chunks as _kb_preview_document_chunks,
)
from fleetent.knowledge_base.management.runtime import (
    update_knowledge_base_description as _kb_update_knowledge_base_description,
)
from fleetent.knowledge_base.retrieval import evaluation as retrieval_evaluation
from fleetent.knowledge_base.retrieval.search import SearchMode
from fleetent.knowledge_base.retrieval.search import search as search_kb
from fleetent.platform.agent_management_console import agent_admin_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.knowledge_base_management import (
    kb_observation as kb_observation_agg,
)
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

router = APIRouter(prefix="/admin/kb")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_DEFAULT_TENANT = "default"
_VALID_MODES = {"vector", "keyword", "hybrid"}
# --- injectable engine seams (knowledge-base / observability follow-ups) -------
# Exact engine signatures are confirmed during host wiring (tasks 0.5); defaults
# here are documented placeholders and are monkeypatched in tests.


def kb_engine_list(tenant_id: str) -> list[dict[str, Any]]:
    """List KBs (kb_id/description/doc_count/chunk_count/last_import/archived)."""
    rows: list[dict[str, Any]] = []
    for row in _kb_list_knowledge_bases(tenant_id, database=_knowledge_database(tenant_id)):
        data = dict(row)
        archived = (
            data.get("archived") if "archived" in data else data.get("archived_at") is not None
        )
        rows.append(
            {
                "tenant_id": data.get("tenant_id"),
                "kb_id": data["kb_id"],
                "description": data.get("description", ""),
                "doc_count": int(data.get("doc_count") or 0),
                "chunk_count": int(data.get("chunk_count") or 0),
                "last_import": data.get("last_import"),
                "archived": bool(archived),
            }
        )
    return rows


def kb_engine_create(tenant_id: str, kb_id: str, description: str) -> None:
    _kb_create_knowledge_base(
        tenant_id, kb_id, description, database=_knowledge_database(tenant_id)
    )


def kb_engine_edit(tenant_id: str, kb_id: str, description: str) -> None:
    if not _kb_update_knowledge_base_description(
        tenant_id, kb_id, description, database=_knowledge_database(tenant_id)
    ):
        raise HTTPException(status_code=404, detail="kb not found")


def kb_engine_archive(tenant_id: str, kb_id: str) -> None:
    with _use_kb_runtime(tenant_id):
        archived = asyncio.run(
            _kb_archive_knowledge_base(
                tenant_id,
                kb_id,
                database=_knowledge_database(tenant_id),
            )
        )
    if not archived:
        raise HTTPException(status_code=404, detail="kb not found or already archived")


def kb_list_documents(tenant_id: str, kb_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in _kb_list_documents(tenant_id, kb_id, database=_knowledge_database(tenant_id))
    ]


def kb_chunk_preview(tenant_id: str, kb_id: str, document_id: str) -> list[dict[str, Any]]:
    return [
        _chunk_to_search_result(chunk)
        for chunk in _kb_preview_document_chunks(
            tenant_id,
            kb_id,
            document_id,
            database=_knowledge_database(tenant_id),
        )
    ]


def kb_delete_document(tenant_id: str, kb_id: str, document_id: str) -> None:
    """Delete a document + cascade its chunks/vectors. Bridges knowledge_base.delete."""
    with _use_kb_runtime(tenant_id):
        deleted = asyncio.run(
            _kb_delete_document(
                tenant_id,
                kb_id,
                document_id,
                database=_knowledge_database(tenant_id),
            )
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="document not found in kb")


def kb_search(
    query: str, tenant_id: str, kb_ids: list[str], mode: str, limit: int
) -> list[dict[str, Any]]:
    """Retrieval test. Bridges knowledge_base.search (vector/keyword/hybrid) on host."""
    search_mode = cast(SearchMode, mode)
    with _use_kb_runtime(tenant_id):
        chunks = asyncio.run(
            search_kb(
                query,
                store=KnowledgeStore(_knowledge_database(tenant_id)),
                tenant_id=tenant_id,
                kb_ids=kb_ids,
                mode=search_mode,
                limit=limit,
            )
        )
    return [_chunk_to_search_result(chunk) for chunk in chunks]


def kb_evaluation(tenant_id: str, kb_id: str) -> dict[str, Any]:
    """Run deterministic retrieval evaluation (read-only). Bridges the eval runner."""
    del tenant_id
    result = asyncio.run(retrieval_evaluation.run_deterministic_fixture_suite())
    return {
        "kb_id": kb_id,
        "metrics": _serialize_retrieval_metrics(result.metrics),
        "hit_ranking": list(result.hit_ranking),
        "fixtures": [
            {
                "name": fixture.fixture_name,
                "document_count": fixture.document_count,
                "metrics": _serialize_retrieval_metrics(fixture.metrics),
                "queries": [
                    {
                        "query": query_result.query,
                        "recall_at_k": query_result.recall_at_k,
                        "forbidden_hits": list(query_result.forbidden_hits),
                        "ranked_hit": (
                            {
                                "rank": query_result.ranked_hit.rank,
                                "reciprocal_rank": query_result.ranked_hit.reciprocal_rank,
                                "matched_snippets": list(query_result.ranked_hit.matched_snippets),
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


def kb_observation(tenant_id: str, kb_id: str) -> dict[str, Any]:
    """Per-kb recall/citation/zero-recall aggregation. Owned by observability."""
    return kb_observation_agg.aggregate(
        tenant_id,
        kb_id,
        agent_kbs_store.list_agents_for_kb(tenant_id, kb_id),
    )


# --- auth helpers -------------------------------------------------------------


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _tenant_router() -> TenantRouter:
    data_dir = create_database(Settings().database_url).path.parent
    return TenantRouter(SQLiteTenantBackend(data_dir=data_dir))


def _knowledge_database(tenant_id: str) -> SQLiteDatabase:
    return _tenant_router().tenant_scope(tenant_id).open_kb_db(KB_MIGRATIONS)


@contextmanager
def _use_kb_runtime(tenant_id: str):
    scope = _tenant_router().tenant_scope(tenant_id)
    previous_db = kb_runtime.runtime._kb_db
    previous_backend = kb_runtime.runtime._kb_vector_backend
    kb_db = scope.open_kb_db(KB_MIGRATIONS)
    kb_runtime.runtime.set_database(kb_db)
    kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)
    try:
        yield scope
    finally:
        kb_runtime.runtime.set_database(previous_db)
        kb_runtime.runtime.set_vector_backend(previous_backend)


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _require_confirm(x_confirm: str | None) -> None:
    if x_confirm != "true":
        raise HTTPException(status_code=428, detail="confirmation required for high-risk action")


# --- request bodies -----------------------------------------------------------


class KbBody(BaseModel):
    kb_id: str
    description: str = ""
    tenant_id: str = _DEFAULT_TENANT


class KbEditBody(BaseModel):
    description: str


class SearchBody(BaseModel):
    query: str
    kb_ids: list[str]
    mode: str = "hybrid"
    top_k: int = 5
    tenant_id: str = _DEFAULT_TENANT


class BindBody(BaseModel):
    agent_id: int
    tenant_id: str = _DEFAULT_TENANT


class EvalBody(BaseModel):
    kb_id: str
    tenant_id: str = _DEFAULT_TENANT


def _require_active_kb(tenant_id: str, kb_id: str) -> None:
    if not _kb_is_active_knowledge_base(tenant_id, kb_id, database=_knowledge_database(tenant_id)):
        raise HTTPException(status_code=404, detail="kb not found or archived")


def _chunk_to_search_result(chunk: KnowledgeChunk) -> dict[str, Any]:
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


def _serialize_retrieval_metrics(
    metrics: retrieval_evaluation.RetrievalMetrics,
) -> dict[str, Any]:
    return {
        "recall_at_k": metrics.recall_at_k,
        "mrr": metrics.mrr,
        "query_count": metrics.query_count,
        "hit_count": metrics.hit_count,
        "hit_rate": metrics.hit_rate,
        "average_hit_rank": metrics.average_hit_rank,
    }


# --- retrieval playground / evaluation / reverse lookup (literal paths first) -


@router.post("/search")
def retrieval_playground(
    body: SearchBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)  # viewer may run read-only
    if body.mode not in _VALID_MODES:
        raise HTTPException(status_code=422, detail=f"unknown mode: {body.mode}")
    if not body.kb_ids:
        raise HTTPException(status_code=422, detail="kb_ids must not be empty")
    results = kb_search(body.query, body.tenant_id, body.kb_ids, body.mode, body.top_k)
    return {"query": body.query, "mode": body.mode, "kb_ids": body.kb_ids, "results": results}


@router.post("/evaluations")
def run_evaluation(body: EvalBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _current_user(authorization)  # read-only analysis, viewer allowed
    result = kb_evaluation(body.tenant_id, body.kb_id)
    audit_log.write_audit(user.id, "kb_eval_run", "kb", body.kb_id)
    return result


@router.get("/by-agent/{agent_id}")
def kbs_for_agent(
    agent_id: int, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    # Archive state lives in the KB engine, not the binding store: drop bindings
    # whose KB has been archived so callers only see live KBs for the agent.
    archived = {kb["kb_id"] for kb in kb_engine_list(tenant_id) if kb.get("archived")}
    kb_ids = [
        kb_id
        for kb_id in agent_kbs_store.list_kbs_for_agent(tenant_id, agent_id)
        if kb_id not in archived
    ]
    return {"agent_id": agent_id, "kb_ids": kb_ids}


# --- KB list / create / edit / archive ----------------------------------------


@router.get("")
def list_kbs(
    tenant_id: str = _DEFAULT_TENANT,
    q: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    rows = []
    for kb in kb_engine_list(tenant_id):
        kb = dict(kb)
        kb["bound_agents"] = agent_kbs_store.list_agents_for_kb(tenant_id, kb["kb_id"])
        if (
            q
            and q.lower() not in kb["kb_id"].lower()
            and q.lower() not in kb.get("description", "").lower()
        ):
            continue
        rows.append(kb)
    return rows


@router.post("")
def create_kb(body: KbBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    existing = {kb["kb_id"] for kb in kb_engine_list(body.tenant_id)}
    if body.kb_id in existing:
        raise HTTPException(status_code=409, detail="kb_id already exists in tenant")
    kb_engine_create(body.tenant_id, body.kb_id, body.description)
    audit_log.write_audit(
        user.id, "kb_create", "kb", body.kb_id, detail={"tenant_id": body.tenant_id}
    )
    return {"kb_id": body.kb_id, "tenant_id": body.tenant_id, "description": body.description}


@router.patch("/{kb_id}")
def edit_kb(
    kb_id: str,
    body: KbEditBody,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    kb_engine_edit(tenant_id, kb_id, body.description)
    audit_log.write_audit(user.id, "kb_edit", "kb", kb_id)
    return {"kb_id": kb_id, "description": body.description}


@router.delete("/{kb_id}")
def archive_kb(
    kb_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if agent_kbs_store.is_kb_bound(tenant_id, kb_id):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "kb still bound to agents",
                "agents": agent_kbs_store.list_agents_for_kb(tenant_id, kb_id),
            },
        )
    _require_confirm(x_confirm)
    kb_engine_archive(tenant_id, kb_id)
    audit_log.write_audit(user.id, "kb_archive", "kb", kb_id)
    return {"kb_id": kb_id, "archived": True}


# --- document list / preview / delete -----------------------------------------


@router.get("/{kb_id}/documents")
def list_documents(
    kb_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return kb_list_documents(tenant_id, kb_id)


@router.get("/{kb_id}/documents/{document_id}/chunks")
def preview_chunks(
    kb_id: str,
    document_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return kb_chunk_preview(tenant_id, kb_id, document_id)


@router.delete("/{kb_id}/documents/{document_id}")
def delete_document(
    kb_id: str,
    document_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    kb_delete_document(tenant_id, kb_id, document_id)
    audit_log.write_audit(user.id, "doc_delete", "kb", kb_id, detail={"document_id": document_id})
    return {"kb_id": kb_id, "document_id": document_id, "deleted": True}


# --- KB ↔ Agent binding matrix ------------------------------------------------


@router.get("/{kb_id}/agents")
def agents_for_kb(
    kb_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    return {"kb_id": kb_id, "agents": agent_kbs_store.list_agents_for_kb(tenant_id, kb_id)}


@router.post("/{kb_id}/agents")
def bind_agent(
    kb_id: str, body: BindBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if any(kb["kb_id"] == kb_id and kb.get("archived") for kb in kb_engine_list(body.tenant_id)):
        raise HTTPException(status_code=409, detail="kb is archived")
    agent_kbs_store.bind(body.tenant_id, kb_id, body.agent_id, created_by=user.id)
    agent_admin_store.touch(body.agent_id)
    audit_log.write_audit(user.id, "kb_bind_agent", "kb", kb_id, detail={"agent_id": body.agent_id})
    return {"kb_id": kb_id, "agent_id": body.agent_id, "bound": True}


@router.delete("/{kb_id}/agents/{agent_id}")
def unbind_agent(
    kb_id: str,
    agent_id: int,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_kbs_store.unbind(tenant_id, kb_id, agent_id)
    agent_admin_store.touch(agent_id)
    audit_log.write_audit(user.id, "kb_unbind_agent", "kb", kb_id, detail={"agent_id": agent_id})
    return {"kb_id": kb_id, "agent_id": agent_id, "bound": False}


# --- per-KB observation -------------------------------------------------------


@router.get("/{kb_id}/observation")
def observation(
    kb_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    return kb_observation(tenant_id, kb_id)
