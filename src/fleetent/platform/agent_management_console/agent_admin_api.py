"""FastAPI router for /admin/agents version + binding management.

Adds the version-listing/activation and the four user/channel binding endpoints on
top of the agent management console, reusing the same Session auth + role guards
(viewer reads, admin writes). Agent rows and bindings come from agent_store; schema
lifecycle is owned by Alembic. This module never imports the agent loop.
"""

import contextlib
from typing import Any

import yaml
from fastapi import APIRouter, Body, Header, HTTPException

from fleetent import agent_config, agent_store, auth, config, user_store
from fleetent.governance import audit_log
from fleetent.platform.connector_management import (
    agent_mcp_server_store,
    agent_oauth_binding_store,
    connector_config_store,
)
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.skill_management import skill_admin_store
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


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


def _require_agent(name: str) -> agent_store.Agent:
    agent = agent_store.get_by_name(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent {name!r} not found")
    return agent


def _known_mcp_server_ids() -> set[str]:
    """The set of MCP server ids an agent may bind to.

    Unions the YAML config seam with DB-registered global servers (admin console),
    matching what ``GET /admin/mcp/servers`` lists — so a server defined only in the
    store (not config) is still bindable.
    """
    ids = {s.id for s in config.load_mcp_server_settings()}
    ids |= {str(r["server_id"]) for r in agent_mcp_server_store.list_mcp_servers(None)}
    return ids


def _build_agent_yaml(agent: agent_store.Agent) -> str:
    """Assemble the runtime agent.yaml from the DB-authored config + bindings.

    Covers every field the admin console authors. connectors.slack is intentionally
    omitted: per-agent Slack connectors are not authored in the DB.
    """
    data: dict[str, Any] = {"name": agent.name}
    if agent.system_prompt:
        data["system_prompt"] = agent.system_prompt
    if agent.model_overrides:
        data["model_overrides"] = agent.model_overrides
    if agent.allowed_skills:
        data["allowed_skills"] = agent.allowed_skills
    if agent.allowed_tools:
        data["allowed_tools"] = agent.allowed_tools
    if agent.plugins:
        data["plugins"] = agent.plugins
    if agent.features:
        data["features"] = agent.features
    if agent.memory_namespace and agent.memory_namespace != "default":
        data["memory_namespace"] = agent.memory_namespace

    servers: list[dict[str, Any]] = []
    for sid in agent_store.list_mcp_servers_for_agent(agent.id):
        row = agent_mcp_server_store.get_mcp_server(
            agent.id, sid
        ) or agent_mcp_server_store.get_mcp_server(None, sid)
        if row is None:
            continue
        entry: dict[str, Any] = {"id": sid, "transport": row["transport"]}
        for key in ("url", "auth_type", "api_key_env", "command", "args", "env"):
            if row.get(key):
                entry[key] = row[key]
        servers.append(entry)
    if servers:
        data["mcp_servers"] = servers

    bindings: dict[str, Any] = {}
    channels = [
        f"{c['platform']}:{c['channel_id']}"
        for c in agent_store.list_channels_for_agent(agent.id)
    ]
    users = agent_store.list_users_for_agent(agent.id)
    if channels:
        bindings["channels"] = channels
    if users:
        bindings["users"] = users
    if bindings:
        data["bindings"] = bindings

    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


@router.get("/agents/{name}/agent-yaml")
def export_agent_yaml(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    return {"agent": name, "yaml": _build_agent_yaml(agent)}


@router.post("/agents/{name}/deploy")
def deploy_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Write the agent.yaml into the runtime agents dir and re-scan so it goes live.

    Target: ``<agents_dir>/<name>/agent.yaml`` (agents_dir resolves under the
    FLEETENT home, e.g. ~/.fleetent/config/agents). Overwrites any existing file.
    """
    user = _require_admin(authorization)
    agent = _require_agent(name)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid agent name")
    dest = agent_config._resolve_agents_dir(None) / name / "agent.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_build_agent_yaml(agent), encoding="utf-8")
    # Best-effort: refresh the in-memory index so the deployed agent is live now.
    # A sibling bad agent.yaml must not fail the deploy.
    with contextlib.suppress(Exception):
        agent_config.scan()
    audit_log.write_audit(
        user.id, "agent.deploy", target_type="agent", target_id=name, detail={"path": str(dest)}
    )
    return {"agent": name, "path": str(dest), "deployed": True}


@router.get("/agents/{name}/versions")
def list_versions(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    _require_agent(name)
    return [
        {
            "id": v.id,
            "version": v.version,
            "is_active": v.is_active,
            "created_at": v.created_at,
        }
        for v in agent_store.list_versions(name)
    ]


@router.post("/agents/{name}/versions/{version}/activate")
def activate_version(
    name: str, version: int, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    _require_agent(name)
    try:
        agent_store.activate_version(name, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"name": name, "active_version": version}


@router.post("/agents/{name}/bindings/users/{user_id}")
def bind_user(name: str, user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.assign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": True}


@router.delete("/agents/{name}/bindings/users/{user_id}")
def unbind_user(
    name: str, user_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.unassign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": False}


@router.post("/agents/{name}/bindings/channels/{platform}/{channel_id}")
def bind_channel(
    name: str,
    platform: str,
    channel_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.assign_channel(platform, channel_id, agent.id)
    return {"agent": name, "platform": platform, "channel_id": channel_id, "bound": True}


@router.delete("/agents/{name}/bindings/channels/{platform}/{channel_id}")
def unbind_channel(
    name: str,
    platform: str,
    channel_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    _require_agent(name)
    agent_store.unassign_channel(platform, channel_id)
    return {"agent": name, "platform": platform, "channel_id": channel_id, "bound": False}


# --- aggregate bindings read --------------------------------------------------


@router.get("/agents/{name}/bindings")
def get_bindings(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    return {
        "users": agent_store.list_users_for_agent(agent.id),
        "channels": agent_store.list_channels_for_agent(agent.id),
        "mcp_servers": agent_store.list_mcp_servers_for_agent(agent.id),
    }


# --- agent-side skill bindings ------------------------------------------------


@router.get("/agents/{name}/skills")
def list_agent_skills(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    _require_agent(name)
    enabled = skill_admin_store.enabled_skill_names(name)
    bound = {
        str(r["skill_name"]): bool(r["enabled"])
        for r in skill_admin_store.list_skills_for_agent(name)
    }
    names = {s["name"] for s in skill_registry.list_skills()} | set(bound)
    return [{"skill_name": n, "enabled": bound.get(n, n in enabled)} for n in sorted(names)]


@router.put("/agents/{name}/skills/{skill_name}")
def set_agent_skill(
    name: str,
    skill_name: str,
    enabled: bool = Body(..., embed=True),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_agent(name)
    skill_admin_store.set_binding(name, skill_name, enabled, updated_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.skill.set",
        target_type="agent",
        target_id=name,
        detail={"skill_name": skill_name, "enabled": enabled},
    )
    return {"agent": name, "skill_name": skill_name, "enabled": enabled}


# --- agent MCP bindings -------------------------------------------------------


@router.post("/agents/{name}/bindings/mcp/{server_id}")
def bind_mcp(name: str, server_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    if server_id not in _known_mcp_server_ids():
        raise HTTPException(status_code=404, detail=f"mcp server {server_id!r} not found")
    agent_store.bind_mcp_server(agent.id, server_id, created_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.mcp.bind",
        target_type="agent",
        target_id=name,
        detail={"server_id": server_id},
    )
    return {"agent": name, "server_id": server_id, "bound": True}


@router.delete("/agents/{name}/bindings/mcp/{server_id}")
def unbind_mcp(
    name: str, server_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.unbind_mcp_server(agent.id, server_id)
    audit_log.write_audit(
        user.id,
        "agent.mcp.unbind",
        target_type="agent",
        target_id=name,
        detail={"server_id": server_id},
    )
    return {"agent": name, "server_id": server_id, "bound": False}


# --- agent knowledge-base bindings -------------------------------------------


@router.get("/agents/{name}/kbs")
def list_agent_kbs(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    kb_ids = agent_kbs_store.list_kbs_for_agent(agent.tenant_id, str(agent.id))
    return {"agent": name, "kb_ids": kb_ids}


@router.post("/agents/{name}/kbs")
def bind_agent_kb(
    name: str,
    kb_id: str = Body(..., embed=True),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_kbs_store.bind(agent.tenant_id, kb_id, str(agent.id), created_by=user.id)
    audit_log.write_audit(
        user.id, "agent.kb.bind", target_type="agent", target_id=name, detail={"kb_id": kb_id}
    )
    return {"agent": name, "kb_id": kb_id, "bound": True}


@router.delete("/agents/{name}/kbs/{kb_id}")
def unbind_agent_kb(
    name: str, kb_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_kbs_store.unbind(agent.tenant_id, kb_id, str(agent.id))
    audit_log.write_audit(
        user.id, "agent.kb.unbind", target_type="agent", target_id=name, detail={"kb_id": kb_id}
    )
    return {"agent": name, "kb_id": kb_id, "bound": False}


# --- agent OAuth connector bindings ------------------------------------------


@router.get("/agents/{name}/bindings/oauth")
def list_agent_oauth(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    connector_ids = agent_oauth_binding_store.list_connectors_for_agent(agent.id)
    return {"agent": name, "connector_ids": connector_ids}


@router.post("/agents/{name}/bindings/oauth/{connector_id}")
def bind_oauth(
    name: str, connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    if connector_config_store.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail=f"connector {connector_id!r} not found")
    agent_oauth_binding_store.bind(agent.id, connector_id, created_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.oauth.bind",
        target_type="agent",
        target_id=name,
        detail={"connector_id": connector_id},
    )
    return {"agent": name, "connector_id": connector_id, "bound": True}


@router.delete("/agents/{name}/bindings/oauth/{connector_id}")
def unbind_oauth(
    name: str, connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_oauth_binding_store.unbind(agent.id, connector_id)
    audit_log.write_audit(
        user.id,
        "agent.oauth.unbind",
        target_type="agent",
        target_id=name,
        detail={"connector_id": connector_id},
    )
    return {"agent": name, "connector_id": connector_id, "bound": False}
