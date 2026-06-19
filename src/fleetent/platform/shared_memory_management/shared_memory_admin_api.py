"""Admin HTTP API for tenant and team scoped shared memory."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, memory, user_store
from fleetent.config import Settings
from fleetent.db import create_database
from fleetent.memory import shared
from fleetent.memory.shared_memory_migrations import MIGRATIONS
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

router = APIRouter(prefix="/admin/memory/shared")

_ADMIN_ROLES = {"admin", "built_in_admin"}
_IDLE_TIMEOUT = 1800
_DEFAULT_TENANT = "default"


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, _IDLE_TIMEOUT)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _tenant_router() -> TenantRouter:
    data_dir = create_database(Settings().database_url).path.parent
    return TenantRouter(SQLiteTenantBackend(data_dir=data_dir))


@contextmanager
def _use_shared_memory_runtime(tenant_id: str):
    scope = _tenant_router().tenant_scope(tenant_id)
    previous_db = shared._shared_memory_db
    previous_backend = shared._shared_memory_vector_backend
    shared.set_shared_memory_db(
        scope.open_shared_memory_db(MIGRATIONS),
        scope.shared_memory_vector_backend,
    )
    try:
        yield
    finally:
        if previous_db is None or previous_backend is None:
            shared._shared_memory_db = previous_db
            shared._shared_memory_vector_backend = previous_backend
        else:
            shared.set_shared_memory_db(previous_db, previous_backend)


def _item_dict(item: Any) -> dict[str, Any]:
    return asdict(item)


class CreateSharedMemoryBody(BaseModel):
    scope_type: str
    scope_id: str
    type: str
    content: str
    tenant_id: str = _DEFAULT_TENANT


class UpdateSharedMemoryBody(BaseModel):
    content: str | None = None
    type: str | None = None
    status: str | None = None
    tenant_id: str = _DEFAULT_TENANT


@router.get("")
def list_shared_memory(
    scope_type: str,
    scope_id: str,
    include_archived: bool = False,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _require_admin(authorization)
    with _use_shared_memory_runtime(tenant_id):
        items = memory.list_shared_memory(
            scope_type,
            scope_id,
            include_archived=include_archived,
        )
    return [_item_dict(item) for item in items]


@router.post("", status_code=201)
async def create_shared_memory_item(
    body: CreateSharedMemoryBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    with _use_shared_memory_runtime(body.tenant_id):
        item = await memory.create_shared_memory(
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            type=body.type,
            content=body.content,
            created_by=admin.id,
        )
    audit_log.write_audit(admin.id, "shared_memory.create", "shared_memory", item.id)
    return _item_dict(item)


@router.patch("/{item_id}")
async def update_shared_memory_item(
    item_id: str,
    body: UpdateSharedMemoryBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    try:
        with _use_shared_memory_runtime(body.tenant_id):
            item = await memory.update_shared_memory(
                item_id,
                content=body.content,
                type=body.type,
                status=body.status,
            )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "does not exist" in detail else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc
    audit_log.write_audit(admin.id, "shared_memory.update", "shared_memory", item.id)
    return _item_dict(item)


@router.post("/{item_id}/archive")
async def archive_shared_memory_item(
    item_id: str,
    tenant_id: str = _DEFAULT_TENANT,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    try:
        with _use_shared_memory_runtime(tenant_id):
            item = await memory.archive_shared_memory(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_log.write_audit(admin.id, "shared_memory.archive", "shared_memory", item.id)
    return _item_dict(item)
