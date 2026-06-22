"""Platform-side node desired-state and status API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from fleetent import agent_store, audit_log
from fleetent.platform import im_gateway_management
from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
from fleetent.platform.agent_management_console import agent_admin_store
from fleetent.platform.node_management import node_store, placement_store
from fleetent.platform.user_management import user_admin_api

router = APIRouter(prefix="/nodes")

_resolve_node_key = node_store.resolve_node_key


class NodeAgentStatusReport(BaseModel):
    agent_id: int
    phase: str
    pid: int | None = None
    health: str | None = None
    detail: str | None = None


class NodeStatusBody(BaseModel):
    agents: list[NodeAgentStatusReport] = Field(default_factory=list)


class NodeIdentityResolveBody(BaseModel):
    tenant_id: str
    channel: str
    platform_user_id: str
    verified_email: str | None = None


class NodeIdentityResolveResponse(BaseModel):
    user_id: str
    tenant_id: str


class NodeLinkConfirmBody(BaseModel):
    platform: str
    platform_user_id: str
    code: str


class NodeLinkConfirmResponse(BaseModel):
    user_id: str
    tenant_id: str
    status: str = "linked"


_pending_links = user_admin_api._pending_links


def _authenticate_node_request(node_id: str, authorization: str | None) -> dict[str, Any]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    identity = _resolve_node_key(api_key)
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid node API key")
    if str(identity["id"]) != node_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return identity


def _authenticate_node(node_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    return _authenticate_node_request(node_id, authorization)


@router.get("/{node_id}/desired-state")
def get_desired_state(
    node_id: str,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    del node
    agents: list[dict[str, Any]] = []
    for placement in placement_store.list_by_node(node_id):
        agent_id = int(placement["agent_id"])
        state = agent_admin_store.get_state(agent_id)
        if state["status"] != "enabled":
            continue
        agent = agent_store.get_by_id(agent_id)
        if agent is None:
            continue
        agents.append(
            {
                "agent_id": agent.id,
                "name": agent.name,
                "config": materialize.desired_state_payload_from_agent_file(
                    materialize.agent_file_from_store(agent)
                ),
                "secrets": _agent_secrets(agent),
            }
        )
    return {"node_id": node_id, "agents": agents}


@router.post("/{node_id}/status")
def post_node_status(
    node_id: str,
    body: NodeStatusBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    del node
    node_store.touch_last_seen(node_id)
    for report in body.agents:
        node_store.upsert_agent_status(
            report.agent_id,
            node_id=node_id,
            phase=report.phase,
            pid=report.pid,
            health=report.health,
            detail=report.detail,
        )
    return {"node_id": node_id, "updated": len(body.agents)}


@router.post("/{node_id}/identity/resolve")
def post_identity_resolve(
    node_id: str,
    body: NodeIdentityResolveBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> NodeIdentityResolveResponse:
    del node, node_id
    user = im_gateway_management.resolve_or_provision(
        body.tenant_id,
        verified_email=body.verified_email,
        channel=body.channel,
        platform_user_id=body.platform_user_id,
    )
    return NodeIdentityResolveResponse(user_id=user.id, tenant_id=user.tenant_id)


@router.post("/{node_id}/link-confirm")
def post_link_confirm(
    node_id: str,
    body: NodeLinkConfirmBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> NodeLinkConfirmResponse:
    del node, node_id
    pending = _pending_links.pop_valid(body.code)
    if pending is None:
        raise HTTPException(status_code=404, detail="invalid or expired link code")
    mapped = im_gateway_management.get_mapped_user(body.platform, body.platform_user_id)
    if mapped is not None and mapped.id != pending.user_id:
        raise HTTPException(status_code=409, detail="identity already mapped")
    user = im_gateway_management.attach_identity(
        body.platform,
        body.platform_user_id,
        pending.user_id,
    )
    audit_log.write_audit(
        pending.user_id,
        "im.link.confirm",
        target_type="im_user",
        target_id=f"{body.platform}:{body.platform_user_id}",
        detail={
            "platform": body.platform,
            "platform_user_id": body.platform_user_id,
            "code_source": "node_im_edge",
        },
    )
    return NodeLinkConfirmResponse(user_id=user.id, tenant_id=user.tenant_id)


def _agent_secrets(agent: agent_store.Agent) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for slot in credential_slots.list_slots(agent):
        if slot.mode != "inject":
            continue
        if secret_store.status(agent.id, slot.env_name) != "set":
            continue
        value = secret_store.get_decrypted(agent.id, slot.env_name)
        if value is not None:
            secrets[slot.env_name] = value
    return secrets
