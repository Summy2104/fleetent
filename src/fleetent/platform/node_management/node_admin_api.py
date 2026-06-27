"""Admin HTTP API for node registry and placements."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fleetent import agent_store, audit_log, auth, user_store
from fleetent.platform.node_management import node_store, placement_store

router = APIRouter(prefix="/admin/nodes")

_ADMIN_ROLES = {"admin"}
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


class RegisterNodeBody(BaseModel):
    node_id: str
    name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class PinNodeBody(BaseModel):
    agent_id: int
    pinned_by: str | None = None


def _serialize_node(node: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in node.items() if key != "key_hash"}


@router.post("")
def register_node(
    body: RegisterNodeBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    try:
        plaintext, node = node_store.register_node(body.node_id, name=body.name, labels=body.labels)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_log.write_audit(user.id, "node.register", target_type="node", target_id=body.node_id)
    return {**_serialize_node(node), "service_key_plaintext_once": plaintext}


@router.get("")
def list_nodes(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _require_admin(authorization)
    return [_serialize_node(node) for node in node_store.list_nodes()]


@router.delete("/{node_id}", status_code=204)
def deregister_node(node_id: str, authorization: str | None = Header(None)) -> Response:
    user = _require_admin(authorization)
    try:
        node_store.deregister_node(node_id)
    except ValueError as exc:
        placements = placement_store.list_by_node(node_id)
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "pinned_agents": [placement["agent_id"] for placement in placements],
            },
        )
    audit_log.write_audit(user.id, "node.deregister", target_type="node", target_id=node_id)
    return Response(status_code=204)


@router.get("/{node_id}/placements")
def list_node_placements(
    node_id: str,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _require_admin(authorization)
    placements = placement_store.list_by_node(node_id)
    result: list[dict[str, Any]] = []
    for placement in placements:
        agent = agent_store.get_by_id(placement["agent_id"])
        result.append({**placement, "agent_name": agent.name if agent is not None else None})
    return result


@router.post("/{node_id}/pin")
def pin_node(
    node_id: str,
    body: PinNodeBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    try:
        placement = placement_store.pin_agent(body.agent_id, node_id, pinned_by=body.pinned_by)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    audit_log.write_audit(
        user.id,
        "node.pin",
        target_type="node",
        target_id=node_id,
        detail={"agent_id": body.agent_id},
    )
    return placement


@router.delete("/{node_id}/pin", status_code=204)
def unpin_node(
    node_id: str,
    agent_id: int,
    authorization: str | None = Header(None),
) -> Response:
    user = _require_admin(authorization)
    placement_store.unpin_agent(agent_id)
    audit_log.write_audit(
        user.id,
        "node.unpin",
        target_type="node",
        target_id=node_id,
        detail={"agent_id": agent_id},
    )
    return Response(status_code=204)
