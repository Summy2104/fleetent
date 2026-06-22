"""FastAPI router for tenancy provisioning admin endpoints.

Authentication: ``Authorization: Session <token>``; all writes require admin role.
Audit: every write calls ``audit_log.write_audit``.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent.platform.tenancy import store as tenancy_store

router = APIRouter(prefix="/admin/tenancy")

_ADMIN_ROLES = {"admin", "built_in_admin"}
_IDLE_TIMEOUT = 1800


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


# ── request bodies ────────────────────────────────────────────────────────────


class CreateTenantBody(BaseModel):
    id: str | None = None
    name: str
    status: str = "active"


class CreateTeamBody(BaseModel):
    id: str | None = None
    tenant_id: str
    name: str


class SetUserTenantBody(BaseModel):
    tenant_id: str


class SetApproverBody(BaseModel):
    entity_type: str  # "tenant" or "team"
    approver_user_id: str | None


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("/tenants")
def api_create_tenant(
    body: CreateTenantBody,
    authorization: str | None = Header(None),
) -> dict:
    admin = _require_admin(authorization)
    tenant = tenancy_store.create_tenant(id=body.id, name=body.name, status=body.status)
    audit_log.write_audit(admin.id, "tenant.create", target_type="tenant", target_id=tenant["id"])
    return tenant


@router.get("/tenants")
def api_list_tenants(
    authorization: str | None = Header(None),
) -> list[dict]:
    _require_admin(authorization)
    return tenancy_store.list_tenants()


@router.post("/teams")
def api_create_team(
    body: CreateTeamBody,
    authorization: str | None = Header(None),
) -> dict:
    admin = _require_admin(authorization)
    team = tenancy_store.create_team(id=body.id, tenant_id=body.tenant_id, name=body.name)
    audit_log.write_audit(admin.id, "team.create", target_type="team", target_id=team["id"])
    return team


@router.get("/teams")
def api_list_teams(
    tenant_id: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict]:
    _require_admin(authorization)
    return tenancy_store.list_teams(tenant_id=tenant_id)


@router.post("/users/{user_id}/tenant")
def api_set_user_tenant(
    user_id: str,
    body: SetUserTenantBody,
    authorization: str | None = Header(None),
) -> dict:
    admin = _require_admin(authorization)
    try:
        tenancy_store.set_user_tenant(user_id, body.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_log.write_audit(
        admin.id,
        "user.set_tenant",
        target_type="user",
        target_id=user_id,
        detail={"tenant_id": body.tenant_id},
    )
    return {"status": "ok", "user_id": user_id, "tenant_id": body.tenant_id}


@router.patch("/approvers/{entity_id}")
def api_set_approver(
    entity_id: str,
    body: SetApproverBody,
    authorization: str | None = Header(None),
) -> dict:
    admin = _require_admin(authorization)
    if body.entity_type == "tenant":
        tenancy_store.set_tenant_approver(entity_id, body.approver_user_id)
        action = "tenant.set_approver"
        target_type = "tenant"
    elif body.entity_type == "team":
        tenancy_store.set_team_approver(entity_id, body.approver_user_id)
        action = "team.set_approver"
        target_type = "team"
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'tenant' or 'team'")
    audit_log.write_audit(
        admin.id,
        action,
        target_type=target_type,
        target_id=entity_id,
        detail={"approver_user_id": body.approver_user_id},
    )
    return {"status": "ok", "entity_type": body.entity_type, "id": entity_id}
