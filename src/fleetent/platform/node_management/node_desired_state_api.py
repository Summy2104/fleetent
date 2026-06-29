"""Platform-side node desired-state and status API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from fleetent import agent_store, audit_log
from fleetent.agent_config import collect_env_var_names
from fleetent.platform import im_gateway_management
from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
from fleetent.platform.agent_management_console import agent_admin_store
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.node_management import node_store, placement_store
from fleetent.platform.skill_management import bundle_cache, skill_admin_store
from fleetent.platform.skill_management.pool_git import pool_version_for_skill
from fleetent.platform.user_management import user_admin_api
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/nodes")

_logger = logging.getLogger(__name__)

_resolve_node_key = node_store.resolve_node_key


class NodeAgentStatusReport(BaseModel):
    agent_id: int
    phase: str
    pid: int | None = None
    health: str | None = None
    detail: str | None = None
    skills: list[NodeSkillStatusReport] = Field(default_factory=list)


class NodeSkillStatusReport(BaseModel):
    skill_name: str
    base_version: str
    base_commit: str
    drift: bool = False


class NodeStatusBody(BaseModel):
    agents: list[NodeAgentStatusReport] = Field(default_factory=list)
    forward_host: str | None = None


class NodeIdentityResolveBody(BaseModel):
    tenant_id: str
    channel: str
    platform_user_id: str
    verified_email: str | None = None


class NodeIdentityResolveResponse(BaseModel):
    user_id: str
    tenant_id: str


class NodeAddressesBody(BaseModel):
    user_id: str


class NodeAddressesResponse(BaseModel):
    addresses: list[dict[str, str]]


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
                "tenant_id": agent.tenant_id,
                "knowledge_resync_epoch": str(state["updated_at"] or ""),
                "config": materialize.desired_state_payload_from_agent_file(
                    materialize.agent_file_from_store(agent)
                ),
                "skill_manifests": _skill_manifests_for(node_id, agent),
                "secrets": _agent_secrets(agent),
            }
        )
    return {"node_id": node_id, "agents": agents}


@router.get("/{node_id}/skills/{skill_name}/bundles/{base_version}.tar.gz")
def get_skill_bundle(
    node_id: str,
    skill_name: str,
    base_version: str,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> FileResponse:
    del node
    artifact = bundle_cache.ensure_bundle_cached(
        pool_dir=_skill_pool_dir(),
        cache_dir=_bundle_cache_dir(),
        skill_name=skill_name,
        base_version=base_version,
    )
    return FileResponse(
        artifact.bundle_path,
        media_type="application/gzip",
        filename=artifact.bundle_path.name,
    )


@router.post("/{node_id}/status")
def post_node_status(
    node_id: str,
    body: NodeStatusBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    del node
    node_store.touch_last_seen(node_id)
    if body.forward_host:
        node_store.set_forward_host(node_id, body.forward_host)
    for report in body.agents:
        node_store.upsert_agent_status(
            report.agent_id,
            node_id=node_id,
            phase=report.phase,
            pid=report.pid,
            health=report.health,
            detail=report.detail,
        )
        _project_skill_status(report)
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


@router.post("/{node_id}/identity/addresses")
def post_identity_addresses(
    node_id: str,
    body: NodeAddressesBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> NodeAddressesResponse:
    del node, node_id
    addresses = im_gateway_management.resolve_user_addresses(body.user_id)
    return NodeAddressesResponse(addresses=addresses)


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


class NodeMcpOAuthPendingBody(BaseModel):
    state: str
    code_verifier: str
    user_id: str
    agent_id: str
    server_id: str
    token_url: str
    client_id: str
    client_secret_env: str = ""
    redirect_uri: str


class NodeMcpOAuthTokenBody(BaseModel):
    user_id: str
    agent_id: str
    server_id: str


class NodeMcpCredentialSetBody(BaseModel):
    user_id: str
    agent_id: str
    server_id: str
    key: str


@router.post("/{node_id}/mcp/oauth-pending")
def post_mcp_oauth_pending(
    node_id: str,
    body: NodeMcpOAuthPendingBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    """Register a per-user OAuth pending-auth on behalf of an agent (via node)."""
    del node, node_id
    from fleetent.platform.connector_management import mcp_oauth_service

    mcp_oauth_service.register_pending(
        state=body.state,
        code_verifier=body.code_verifier,
        user_id=body.user_id,
        agent_id=body.agent_id,
        server_id=body.server_id,
        token_url=body.token_url,
        client_id=body.client_id,
        client_secret_env=body.client_secret_env,
        redirect_uri=body.redirect_uri,
    )
    return {"ok": True}


@router.post("/{node_id}/mcp/oauth-token")
async def post_mcp_oauth_token(
    node_id: str,
    body: NodeMcpOAuthTokenBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    """Return a valid per-user access token (transparent refresh); never the refresh token."""
    del node, node_id
    from fleetent.platform.connector_management import mcp_oauth_service

    access_token = await mcp_oauth_service.fetch_access_token(
        body.user_id, body.agent_id, body.server_id
    )
    if access_token is None:
        raise HTTPException(status_code=404, detail="no token; authorization required")
    return {"access_token": access_token}


@router.post("/{node_id}/mcp/credential-set")
def post_mcp_credential_set(
    node_id: str,
    body: NodeMcpCredentialSetBody,
    node: dict[str, Any] = Depends(_authenticate_node),  # noqa: B008
) -> dict[str, Any]:
    """Store a user-supplied static api-key on behalf of an agent (mode 2 tool, via node)."""
    del node, node_id
    from fleetent.platform.connector_management import mcp_oauth_service

    mcp_oauth_service.store_static_credential(body.user_id, body.agent_id, body.server_id, body.key)
    return {"ok": True}


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
    # Seed model env from the provider row (shared source of truth) for any referenced env
    # name not already supplied by a per-agent inject slot, mirroring materialize._seed_env so
    # node-managed agents resolve the same model key as platform-direct materialize.
    agent_file = materialize.agent_file_from_store(agent)
    for env_name in collect_env_var_names(agent_file):
        if env_name in secrets:
            continue
        provider_key = provider_admin_store.provider_key_for_env(env_name)
        if provider_key:
            secrets[env_name] = provider_key
    return secrets


def _project_skill_status(report: NodeAgentStatusReport) -> None:
    from fleetent.platform.skill_management import backflow_store, skill_admin_store

    for skill in report.skills:
        skill_admin_store.set_base_version(report.agent_id, skill.skill_name, skill.base_version)
        skill_admin_store.set_base_commit(report.agent_id, skill.skill_name, skill.base_commit)
        skill_admin_store.set_drift(report.agent_id, skill.skill_name, drifted=skill.drift)
        if skill.drift:
            # Best-effort auto-nomination: a failed bundle capture (e.g. the owning
            # node is briefly unreachable) must not fail status ingestion.
            try:
                backflow_store.nominate_if_absent(
                    agent_id=report.agent_id,
                    skill_name=skill.skill_name,
                    pool_dir=_skill_pool_dir(),
                )
            except Exception:
                _logger.warning(
                    "auto-nominate backflow failed for agent=%s skill=%s",
                    report.agent_id,
                    skill.skill_name,
                    exc_info=True,
                )


def _skill_manifests_for(node_id: str, agent: agent_store.Agent) -> list[dict[str, str]]:
    pool_dir = _skill_pool_dir()
    manifests: list[dict[str, str]] = []
    for skill_name in materialize.agent_file_from_store(agent).allowed_skills:
        skill_dir = pool_dir / skill_name
        if not skill_dir.is_dir():
            continue
        base_version = bundle_cache.skill_directory_version(skill_dir)
        artifact = bundle_cache.ensure_bundle_cached(
            pool_dir=pool_dir,
            cache_dir=_bundle_cache_dir(),
            skill_name=skill_name,
            base_version=base_version,
        )
        manifests.append(
            {
                "name": skill_name,
                "base_version": base_version,
                "base_commit": pool_version_for_skill(pool_dir, skill_name) or "",
                "bundle_url": (
                    f"/nodes/{node_id}/skills/{skill_name}/bundles/{base_version}.tar.gz"
                ),
                "bundle_sha256": artifact.bundle_sha256,
                "resync_epoch": str(skill_admin_store.get_resync_epoch(agent.id, skill_name)),
            }
        )
    return manifests


def _skill_pool_dir() -> Path:
    return Path(skill_registry._resolve_skills_dir(None))


def _bundle_cache_dir() -> Path:
    from fleetent import paths

    return paths.base_dir() / "skill-bundles"
