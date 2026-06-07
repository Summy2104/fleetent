"""FastAPI router for /admin/kb — the knowledge-base management face.

Owns the management behaviour only: KB listing/create/edit/archive with binding
protection, document import (paste/upload + local-directory sync), document list /
chunk preview / single-document delete, the retrieval test playground, the KB↔Agent
binding matrix, the evaluation entry, and the per-KB observation view.

Parsing / chunking / indexing / vector·keyword·hybrid retrieval / tenant-isolated
recall live in the knowledge-base engine; recall injection + token budget live in
long-term-ctx; per-kb aggregation lives in observability. Those are reached through
injectable seams (mockable in tests). Only the agent_kbs binding is persisted here.
This router never imports the agent loop, so it is testable in isolation.

Auth mirrors user_admin_api: reads allow viewer+admin, writes require admin.
"""

import asyncio
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.governance import audit_log
from fleetent.intelligence import knowledge_base
from fleetent.platform.knowledge_base_management import agent_kbs_store, kb_connector_store
from fleetent.platform.secret_management import agent_secret_store, credential_service

router = APIRouter(prefix="/admin/kb")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
_DEFAULT_TENANT = "default"
_VALID_MODES = {"vector", "keyword", "hybrid"}


# --- injectable engine seams (knowledge-base / observability follow-ups) -------
# Exact engine signatures are confirmed during host wiring (tasks 0.5); defaults
# here are documented placeholders and are monkeypatched in tests.


def kb_engine_list(tenant_id: str) -> list[dict[str, Any]]:
    """List KBs (kb_id/description/doc_count/chunk_count/last_import/archived)."""
    return [dict(row) for row in knowledge_base.list_knowledge_bases(tenant_id)]


def kb_engine_create(tenant_id: str, kb_id: str, description: str) -> None:
    knowledge_base.create_knowledge_base(tenant_id, kb_id, description)


def kb_engine_edit(tenant_id: str, kb_id: str, description: str) -> None:
    if not knowledge_base.update_knowledge_base_description(tenant_id, kb_id, description):
        raise HTTPException(status_code=404, detail="kb not found")


def kb_engine_archive(tenant_id: str, kb_id: str) -> None:
    archived = asyncio.run(knowledge_base.archive_knowledge_base(tenant_id, kb_id))
    if not archived:
        raise HTTPException(status_code=404, detail="kb not found or already archived")


def kb_ingest_text(
    tenant_id: str, kb_id: str, source: str, content: str, document_format: str
) -> dict[str, Any]:
    """Ingest pasted/uploaded content. Bridges knowledge_base.ingest_text on host."""
    _require_active_kb(tenant_id, kb_id)
    parsed = _parse_import_document(source, content, document_format)
    document = asyncio.run(
        knowledge_base.ingest_parsed(
            parsed,
            tenant_id=tenant_id,
            kb_id=kb_id,
            source=source,
        )
    )
    chunks = knowledge_base.preview_document_chunks(tenant_id, kb_id, document.id)
    return {
        "document_id": document.id,
        "chunks": len(chunks),
        "filename": document.filename,
        "source": document.source,
        "source_url": document.source_url,
        "wired": True,
    }


def kb_sync_directory(tenant_id: str, kb_id: str, path: str) -> dict[str, Any]:
    """Sync a local directory source. Bridges connectors.sync_local_directory on host."""
    _require_active_kb(tenant_id, kb_id)
    try:
        config = knowledge_base.LocalDirectorySourceConfig(
            source_id=f"admin-local:{tenant_id}:{kb_id}:{Path(path).expanduser().resolve()}",
            root_path=path,
            allowed_roots=[path],
        )
        plan = asyncio.run(
            knowledge_base.plan_local_directory_sync(config, tenant_id=tenant_id, kb_id=kb_id)
        )
        summary = asyncio.run(knowledge_base.execute_sync_plan(plan))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "scanned": summary.scanned,
        "ingested": summary.ingested,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "unsupported": summary.unsupported,
        "unchanged": summary.unchanged,
        "deleted": summary.deleted,
        "archived": summary.archived,
        "changed": summary.changed,
        "auth_failed": summary.auth_failed,
        "wired": True,
    }


def kb_list_documents(tenant_id: str, kb_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in knowledge_base.list_documents(tenant_id, kb_id)]


def kb_chunk_preview(tenant_id: str, kb_id: str, document_id: str) -> list[dict[str, Any]]:
    return [
        dict(row) for row in knowledge_base.preview_document_chunks(tenant_id, kb_id, document_id)
    ]


def kb_delete_document(tenant_id: str, kb_id: str, document_id: str) -> None:
    """Delete a document + cascade its chunks/vectors. Bridges knowledge_base.delete."""
    deleted = asyncio.run(knowledge_base.delete_document(tenant_id, kb_id, document_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="document not found in kb")


def kb_search(
    query: str, tenant_id: str, kb_ids: list[str], mode: str, limit: int
) -> list[dict[str, Any]]:
    """Retrieval test. Bridges knowledge_base.search (vector/keyword/hybrid) on host."""
    search_mode = cast(knowledge_base.SearchMode, mode)
    chunks = asyncio.run(
        knowledge_base.search(
            query,
            tenant_id=tenant_id,
            kb_ids=kb_ids,
            mode=search_mode,
            limit=limit,
        )
    )
    return [_chunk_to_search_result(chunk) for chunk in chunks]


def kb_evaluation(tenant_id: str, kb_id: str) -> dict[str, Any]:
    """Run deterministic retrieval evaluation (read-only). Bridges the eval runner."""
    return {"kb_id": kb_id, "metrics": {}, "wired": False}


def kb_observation(tenant_id: str, kb_id: str) -> dict[str, Any]:
    """Per-kb recall/citation/zero-recall aggregation. Owned by observability."""
    return {"kb_id": kb_id, "recall_hits": 0, "zero_recall_docs": [], "sessions": []}


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


class ImportBody(BaseModel):
    source: str
    content: str
    document_format: str = "text"
    tenant_id: str = _DEFAULT_TENANT


class SyncBody(BaseModel):
    path: str
    tenant_id: str = _DEFAULT_TENANT


class SearchBody(BaseModel):
    query: str
    kb_ids: list[str]
    mode: str = "hybrid"
    top_k: int = 5
    tenant_id: str = _DEFAULT_TENANT


class BindBody(BaseModel):
    agent_id: str
    tenant_id: str = _DEFAULT_TENANT


class EvalBody(BaseModel):
    kb_id: str
    tenant_id: str = _DEFAULT_TENANT


def _parse_import_document(
    source: str, content: str, document_format: str
) -> knowledge_base.ParsedDocument:
    normalized_format = document_format.lower()
    if normalized_format in {"text", "txt"}:
        return knowledge_base.parse_text(source, content)
    if normalized_format in {"markdown", "md"}:
        return knowledge_base.parse_markdown(source, content)
    if normalized_format in {"html", "htm"}:
        return knowledge_base.parse_html(source, content)
    raise HTTPException(status_code=422, detail=f"unsupported document_format: {document_format}")


def _require_active_kb(tenant_id: str, kb_id: str) -> None:
    if not knowledge_base.is_active_knowledge_base(tenant_id, kb_id):
        raise HTTPException(status_code=404, detail="kb not found or archived")


def _chunk_to_search_result(chunk: knowledge_base.KnowledgeChunk) -> dict[str, Any]:
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
    agent_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
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


# --- document import / list / preview / delete --------------------------------


@router.post("/{kb_id}/documents")
def import_document(
    kb_id: str, body: ImportBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = kb_ingest_text(body.tenant_id, kb_id, body.source, body.content, body.document_format)
    audit_log.write_audit(
        user.id,
        "doc_import",
        "kb",
        kb_id,
        detail={"source": body.source, "format": body.document_format},
    )
    return result


@router.post("/{kb_id}/sync")
def sync_directory(
    kb_id: str,
    body: SyncBody,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)  # full resync is high-risk
    result = kb_sync_directory(body.tenant_id, kb_id, body.path)
    audit_log.write_audit(user.id, "doc_sync", "kb", kb_id, detail={"path": body.path})
    return result


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
    audit_log.write_audit(user.id, "kb_bind_agent", "kb", kb_id, detail={"agent_id": body.agent_id})
    return {"kb_id": kb_id, "agent_id": body.agent_id, "bound": True}


@router.delete("/{kb_id}/agents/{agent_id}")
def unbind_agent(
    kb_id: str,
    agent_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_kbs_store.unbind(tenant_id, kb_id, agent_id)
    audit_log.write_audit(user.id, "kb_unbind_agent", "kb", kb_id, detail={"agent_id": agent_id})
    return {"kb_id": kb_id, "agent_id": agent_id, "bound": False}


# --- per-KB observation -------------------------------------------------------


@router.get("/{kb_id}/observation")
def observation(
    kb_id: str, tenant_id: str = _DEFAULT_TENANT, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    return kb_observation(tenant_id, kb_id)


# --- KB source connectors (Google Drive / Confluence) -------------------------
#
# DB-managed ingestion connectors. The stored config + credential env-references are
# assembled into a KnowledgeBaseSettings and fed to the existing config-driven
# ingestion engine (operations.*), so check/status/sync are reused unchanged. Real
# ingestion sync stays gated to the CLI; the console exposes check + dry-run + status.


class ConnectorBody(BaseModel):
    connector_id: str
    kind: str  # google_drive | confluence
    tenant_id: str = _DEFAULT_TENANT
    kb_id: str = "global"
    enabled: bool = True
    # A connector IS a knowledge base: this short description lives on the KB it targets
    # and is shown when agents pick the KB.
    description: str = ""
    config: dict[str, Any] = {}
    custom: dict[str, Any] = {}  # free-form metadata, not schema-filtered
    # Console sends custom as YAML (friendlier to author); parsed server-side. When
    # present it overrides `custom`. Stored as JSON either way.
    custom_yaml: str | None = None


class ConnectorEditBody(BaseModel):
    tenant_id: str | None = None
    kb_id: str | None = None
    enabled: bool | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    custom: dict[str, Any] | None = None
    custom_yaml: str | None = None


def _parse_custom_yaml(text: str) -> dict[str, Any]:
    """Parse the YAML the user authored into a dict (empty/blank -> {})."""
    if not text or not text.strip():
        return {}
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"invalid custom YAML: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="custom must be a YAML mapping")
    return parsed


def _kb_description(tenant_id: str, kb_id: str) -> str:
    """The description stored on the KB this connector targets (empty if none)."""
    for kb in kb_engine_list(tenant_id):
        if kb["kb_id"] == kb_id:
            return str(kb.get("description") or "")
    return ""


def _apply_kb_description(tenant_id: str, kb_id: str, description: str) -> None:
    """A connector IS a KB: ensure the KB row exists and set its description."""
    knowledge_base.create_knowledge_base(tenant_id, kb_id, description)
    knowledge_base.update_knowledge_base_description(tenant_id, kb_id, description)


def _resolve_inline_secrets(connector_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Encrypt inline token values into the shared secret scope, leaving only env refs.

    A ``<field>_env_value`` key carries a secret typed inline (value mode). We store it
    encrypted under a derived name and set ``<field>_env`` to that name — the config blob,
    like ``agent.yaml``, only ever holds ``*_env`` references, never a secret value.
    """
    resolved = dict(config)
    for key in [k for k in resolved if k.endswith("_env_value")]:
        value = resolved.pop(key)
        if not value:
            continue
        field = key[: -len("_value")]  # access_token_env_value -> access_token_env
        env_name = credential_service.derive_kb_env_name(connector_id, field)
        agent_secret_store.set_secret(None, env_name, str(value))
        resolved[field] = env_name
    return resolved


def _connector_out(row: dict[str, Any]) -> dict[str, Any]:
    """Augment a stored connector with custom_yaml + its KB description for display/editing."""
    out = dict(row)
    custom = out.get("custom") or {}
    out["custom_yaml"] = (
        yaml.safe_dump(custom, sort_keys=False, allow_unicode=True) if custom else ""
    )
    out["description"] = _kb_description(str(out.get("tenant_id", "")), str(out.get("kb_id", "")))
    return out


def _connector_settings() -> Any:
    """A settings-shaped object exposing .knowledge_base built from the DB store,
    so the config-driven ingestion engine can run against DB-managed connectors."""
    from types import SimpleNamespace

    return SimpleNamespace(knowledge_base=kb_connector_store.as_knowledge_base_settings())


@router.get("/connectors")
def list_kb_connectors(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_connector_out(r) for r in kb_connector_store.list_connectors()]


@router.post("/connectors", status_code=201)
def add_kb_connector(
    body: ConnectorBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if body.kind not in kb_connector_store.KINDS:
        raise HTTPException(status_code=422, detail=f"unknown kind: {body.kind}")
    if kb_connector_store.get_connector(body.connector_id) is not None:
        raise HTTPException(status_code=409, detail="connector id already exists")
    custom = _parse_custom_yaml(body.custom_yaml) if body.custom_yaml is not None else body.custom
    try:
        config = _resolve_inline_secrets(body.connector_id, body.config)
    except agent_secret_store.SecretKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        kb_connector_store.add_connector(
            body.connector_id,
            body.kind,
            body.tenant_id,
            body.kb_id,
            config,
            body.enabled,
            custom=custom,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _apply_kb_description(body.tenant_id, body.kb_id, body.description)
    audit_log.write_audit(user.id, "kb_connector.add", "kb_connector", body.connector_id)
    created = kb_connector_store.get_connector(body.connector_id)
    assert created is not None
    return _connector_out(created)


@router.patch("/connectors/{connector_id}")
def edit_kb_connector(
    connector_id: str, body: ConnectorEditBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    fields = body.model_dump(exclude_unset=True)
    if "custom_yaml" in fields:
        fields["custom"] = _parse_custom_yaml(fields.pop("custom_yaml"))
    # description lives on the KB, not the connector row — handle it separately.
    description = fields.pop("description", None)
    if "config" in fields:
        try:
            fields["config"] = _resolve_inline_secrets(connector_id, fields["config"])
        except agent_secret_store.SecretKeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        kb_connector_store.edit_connector(connector_id, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    edited = kb_connector_store.get_connector(connector_id)
    if edited is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if description is not None:
        _apply_kb_description(edited["tenant_id"], edited["kb_id"], description)
    audit_log.write_audit(user.id, "kb_connector.edit", "kb_connector", connector_id)
    return _connector_out(edited)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_kb_connector(connector_id: str, authorization: str | None = Header(None)) -> None:
    user = _require_admin(authorization)
    if not kb_connector_store.delete_connector(connector_id):
        raise HTTPException(status_code=404, detail="connector not found")
    audit_log.write_audit(user.id, "kb_connector.delete", "kb_connector", connector_id)


@router.post("/connectors/{connector_id}/check")
async def check_kb_connector(
    connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    if kb_connector_store.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    result = await knowledge_base.check_connector(connector_id, settings=_connector_settings())
    return {"connector_id": result.connector_id, "status": result.status, "message": result.message}


@router.get("/connectors/{connector_id}/status")
def kb_connector_status(
    connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    if kb_connector_store.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    status = knowledge_base.get_connector_status(connector_id, settings=_connector_settings())
    return {
        "connector_id": status.connector_id,
        "status": status.last_status,
        "summary": status.last_summary,
        "error": status.last_error,
    }


class ConnectorSyncBody(BaseModel):
    dry_run: bool = True


@router.post("/connectors/{connector_id}/sync")
async def sync_kb_connector(
    connector_id: str,
    body: ConnectorSyncBody,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if kb_connector_store.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if not body.dry_run:
        _require_confirm(x_confirm)  # real ingestion is high-risk
    result = await knowledge_base.run_connector_sync(
        connector_id, settings=_connector_settings(), dry_run=body.dry_run
    )
    audit_log.write_audit(
        user.id,
        "kb_connector.sync",
        "kb_connector",
        connector_id,
        detail={"dry_run": body.dry_run, "status": result.status},
    )
    return {
        "connector_id": result.connector_id,
        "status": result.status,
        "summary": result.summary,
        "error": result.error,
    }
