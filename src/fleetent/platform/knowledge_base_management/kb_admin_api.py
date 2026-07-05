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

from typing import Any, NoReturn, cast

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent.config import Settings
from fleetent.knowledge_base.retrieval.search import SearchMode
from fleetent.platform.agent_management_console import agent_admin_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.knowledge_base_management import (
    kb_observation as kb_observation_agg,
)
from fleetent.platform.knowledge_base_management.kb_serve_client import KBServeClient

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
    for row in get_kb_serve_client().list_knowledge_bases(tenant_id):
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
    get_kb_serve_client().create_knowledge_base(tenant_id, kb_id, description)


def kb_engine_edit(tenant_id: str, kb_id: str, description: str) -> None:
    get_kb_serve_client().update_knowledge_base(tenant_id, kb_id, description=description)


def kb_engine_archive(tenant_id: str, kb_id: str) -> None:
    get_kb_serve_client().archive_knowledge_base(tenant_id, kb_id)


def kb_list_documents(tenant_id: str, kb_id: str) -> list[dict[str, Any]]:
    return get_kb_serve_client().list_documents(tenant_id, kb_id)


def kb_chunk_preview(tenant_id: str, kb_id: str, document_id: str) -> list[dict[str, Any]]:
    return get_kb_serve_client().preview_document_chunks(tenant_id, kb_id, document_id)


def kb_delete_document(tenant_id: str, kb_id: str, document_id: str) -> None:
    """Delete a document + cascade its chunks/vectors. Bridges knowledge_base.delete."""
    get_kb_serve_client().delete_document(tenant_id, kb_id, document_id)


def kb_search(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    mode: str,
    limit: int,
    *,
    rerank: bool,
    use_planner: bool,
) -> list[dict[str, Any]]:
    """Retrieval test. Bridges knowledge_base.search (vector/keyword/hybrid) on host."""
    search_mode = cast(SearchMode, mode)
    return cast(
        list[dict[str, Any]],
        get_kb_serve_client().search(
            tenant_id=tenant_id,
            query=query,
            kb_ids=kb_ids,
            limit=limit,
            mode=search_mode,
            rerank=rerank,
            use_planner=use_planner,
        )["chunks"],
    )


def kb_evaluation(tenant_id: str, kb_id: str) -> dict[str, Any]:
    """Run deterministic retrieval evaluation (read-only). Bridges the eval runner."""
    return get_kb_serve_client().run_evaluation(tenant_id, kb_id)


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


def get_kb_serve_client() -> KBServeClient:
    settings = Settings().kb_serve
    if not settings.url.strip():
        raise HTTPException(status_code=503, detail="kb serve url is not configured")
    if not settings.service_key_ref.strip():
        raise HTTPException(status_code=503, detail="kb serve service key is not configured")
    return KBServeClient(settings)


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
    rerank: bool = False
    use_planner: bool = False
    tenant_id: str = _DEFAULT_TENANT


class BindBody(BaseModel):
    agent_id: int
    tenant_id: str = _DEFAULT_TENANT


class EvalBody(BaseModel):
    kb_id: str
    tenant_id: str = _DEFAULT_TENANT


def _raise_as_http_exception(exc: httpx.HTTPStatusError) -> NoReturn:
    detail: Any
    try:
        payload = exc.response.json()
    except ValueError:
        detail = exc.response.text or exc.response.reason_phrase
    else:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
    raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc


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
    try:
        results = kb_search(
            body.query,
            body.tenant_id,
            body.kb_ids,
            body.mode,
            body.top_k,
            rerank=body.rerank,
            use_planner=body.use_planner,
        )
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    return {"query": body.query, "mode": body.mode, "kb_ids": body.kb_ids, "results": results}


@router.post("/evaluations")
def run_evaluation(body: EvalBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _current_user(authorization)  # read-only analysis, viewer allowed
    try:
        result = kb_evaluation(body.tenant_id, body.kb_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    audit_log.write_audit(user.id, "kb_eval_run", "kb", body.kb_id)
    return result


# --- KB list / create / edit / archive ----------------------------------------


@router.get("")
def list_kbs(
    tenant_id: str = _DEFAULT_TENANT,
    q: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    rows = []
    try:
        kb_rows = kb_engine_list(tenant_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    for kb in kb_rows:
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
    try:
        existing = {kb["kb_id"] for kb in kb_engine_list(body.tenant_id)}
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    if body.kb_id in existing:
        raise HTTPException(status_code=409, detail="kb_id already exists in tenant")
    try:
        kb_engine_create(body.tenant_id, body.kb_id, body.description)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
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
    try:
        kb_engine_edit(tenant_id, kb_id, body.description)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
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
    try:
        kb_engine_archive(tenant_id, kb_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    audit_log.write_audit(user.id, "kb_archive", "kb", kb_id)
    return {"kb_id": kb_id, "archived": True}


# --- document list / preview / delete -----------------------------------------


@router.get("/{kb_id}/documents")
def list_documents(
    kb_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    try:
        return kb_list_documents(tenant_id, kb_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)


@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    try:
        result = get_kb_serve_client().upload_document(
            tenant_id,
            kb_id,
            filename=file.filename or "upload.bin",
            content=await file.read(),
            content_type=file.content_type or "application/octet-stream",
        )
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
    audit_log.write_audit(
        user.id,
        "doc_upload",
        "kb",
        kb_id,
        detail={"filename": file.filename or "upload.bin"},
    )
    return result


@router.get("/{kb_id}/documents/{document_id}/chunks")
def preview_chunks(
    kb_id: str,
    document_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    try:
        return kb_chunk_preview(tenant_id, kb_id, document_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)


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
    try:
        kb_delete_document(tenant_id, kb_id, document_id)
    except httpx.HTTPStatusError as exc:
        _raise_as_http_exception(exc)
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
