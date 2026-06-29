"""FastAPI router for /admin/agents binding management.

Adds the user/group/MCP/secret binding endpoints on top of the agent management
console, reusing the same Session auth + role guards (viewer reads, admin
writes). Agent rows and bindings come from agent_store; schema lifecycle is
owned by Alembic. This module never imports the agent loop.
"""

from typing import Any

import yaml
from fastapi import APIRouter, Body, Header, HTTPException, Response, status
from pydantic import BaseModel

from fleetent import agent_store, audit_log, auth, user_store
from fleetent.platform.agent_lifecycle import credential_slots, secret_store
from fleetent.platform.agent_lifecycle.materialize import agent_file_from_store
from fleetent.platform.agent_management_console import agent_admin_store, agent_im_group_store
from fleetent.platform.connector_management import (
    mcp_server_store,
)
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.skill_management import skill_admin_store
from fleetent.skills import registry as skill_registry


class _AgentYamlDumper(yaml.Dumper):
    """Dump agent.yaml the way the hand-written examples read: sequence items indented
    under their key, and multiline strings as literal block scalars."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        # Force indented (non-indentless) block sequences: "key:\n  - item".
        return super().increase_indent(flow, False)


def _represent_str(dumper: yaml.Dumper, data: str) -> Any:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_AgentYamlDumper.add_representer(str, _represent_str)


router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}


class SecretWriteBody(BaseModel):
    value: str


class AgentImGroupBindingBody(BaseModel):
    platform: str
    group_id: str


class AgentImCapabilitiesBody(BaseModel):
    supports_dm: bool
    supports_groups: bool


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

    Uses DB-registered global servers (admin console), matching what
    ``GET /admin/mcp/servers`` lists.
    """
    return {str(r["server_id"]) for r in mcp_server_store.list_mcp_servers(None)}


def _build_agent_yaml(agent: agent_store.Agent) -> str:
    """Assemble the runtime agent.yaml from the DB-authored config + bindings.

    Covers every field the admin console authors. im.slack is intentionally
    omitted: per-agent Slack IM bindings are not authored in the DB.
    """
    data: dict[str, Any] = agent_file_from_store(agent).model_dump(
        mode="json", exclude_defaults=False
    )

    bindings: dict[str, Any] = dict(data.get("bindings") or {})
    users = agent_store.list_users_for_agent(agent.id)
    if users:
        bindings["users"] = users
    if bindings:
        data["bindings"] = bindings

    return yaml.dump(
        data,
        Dumper=_AgentYamlDumper,
        indent=2,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


@router.get("/agents/{name}/agent-yaml")
def export_agent_yaml(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    return {"agent": name, "yaml": _build_agent_yaml(agent)}


@router.put("/agents/{name}/default")
def set_default_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_admin_store.set_default(agent.id)
    audit_log.write_audit(user.id, "agent.default.set", target_type="agent", target_id=name)
    return {"agent": name, "is_default": True}


@router.delete("/agents/default")
def clear_default_agent(authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.clear_default()
    audit_log.write_audit(user.id, "agent.default.clear", target_type="agent", target_id="*")
    return {"cleared": True}


@router.post("/agents/{name}/users/{user_id}")
def bind_user(name: str, user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.assign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": True}


@router.delete("/agents/{name}/users/{user_id}")
def unbind_user(
    name: str, user_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.unassign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": False}


@router.post("/agents/{name}/groups", status_code=status.HTTP_201_CREATED)
def bind_im_group(
    name: str,
    body: AgentImGroupBindingBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_im_group_store.bind(agent.id, body.platform, body.group_id, created_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.im_group.bind",
        target_type="agent",
        target_id=name,
        detail={"platform": body.platform, "group_id": body.group_id},
    )
    return {"agent": name, "platform": body.platform, "group_id": body.group_id, "bound": True}


@router.delete(
    "/agents/{name}/groups/{platform}/{group_id}", status_code=status.HTTP_204_NO_CONTENT
)
def unbind_im_group(
    name: str,
    platform: str,
    group_id: str,
    authorization: str | None = Header(None),
) -> Response:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_im_group_store.unbind(agent.id, platform, group_id)
    audit_log.write_audit(
        user.id,
        "agent.im_group.unbind",
        target_type="agent",
        target_id=name,
        detail={"platform": platform, "group_id": group_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/agents/{name}/im-capabilities")
def set_im_capabilities(
    name: str,
    body: AgentImCapabilitiesBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_agent(name)
    agent_store.set_im_capabilities(
        name,
        supports_dm=body.supports_dm,
        supports_groups=body.supports_groups,
    )
    audit_log.write_audit(
        user.id,
        "agent.im_capabilities.set",
        target_type="agent",
        target_id=name,
        detail={
            "supports_dm": body.supports_dm,
            "supports_groups": body.supports_groups,
        },
    )
    return {
        "agent": name,
        "supports_dm": body.supports_dm,
        "supports_groups": body.supports_groups,
    }


# --- per-type bindings read ---------------------------------------------------


@router.get("/agents/{name}/users")
def list_agent_users(name: str, authorization: str | None = Header(None)) -> list[str]:
    _current_user(authorization)
    agent = _require_agent(name)
    return agent_store.list_users_for_agent(agent.id)


@router.get("/agents/{name}/groups")
def list_agent_groups(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    agent = _require_agent(name)
    return agent_im_group_store.list_groups_for_agent(agent.id)


@router.get("/agents/{name}/mcp")
def list_agent_mcp_servers(name: str, authorization: str | None = Header(None)) -> list[str]:
    _current_user(authorization)
    agent = _require_agent(name)
    return agent_store.list_mcp_servers_for_agent(agent.id)


# --- agent-side skill bindings ------------------------------------------------


@router.get("/agents/{name}/skills")
def list_agent_skills(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    agent = _require_agent(name)
    enabled = skill_admin_store.enabled_skill_names(agent.id)
    bound = {
        str(r["skill_name"]): bool(r["enabled"])
        for r in skill_admin_store.list_skills_for_agent(agent.id)
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
    agent = _require_agent(name)
    skill_admin_store.set_binding(agent.id, skill_name, enabled, updated_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.skill.set",
        target_type="agent",
        target_id=name,
        detail={"skill_name": skill_name, "enabled": enabled},
    )
    return {"agent": name, "skill_name": skill_name, "enabled": enabled}


# --- agent MCP bindings -------------------------------------------------------


@router.post("/agents/{name}/mcp/{server_id}")
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


@router.delete("/agents/{name}/mcp/{server_id}")
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
    kb_ids = agent_kbs_store.list_kbs_for_agent(agent.tenant_id, agent.id)
    return {"agent": name, "kb_ids": kb_ids}


@router.post("/agents/{name}/kbs")
def bind_agent_kb(
    name: str,
    kb_id: str = Body(..., embed=True),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_kbs_store.bind(agent.tenant_id, kb_id, agent.id, created_by=user.id)
    agent_admin_store.touch(agent.id)
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
    agent_kbs_store.unbind(agent.tenant_id, kb_id, agent.id)
    agent_admin_store.touch(agent.id)
    audit_log.write_audit(
        user.id, "agent.kb.unbind", target_type="agent", target_id=name, detail={"kb_id": kb_id}
    )
    return {"agent": name, "kb_id": kb_id, "bound": False}


# --- agent credential slots / secrets ----------------------------------------


@router.get("/agents/{name}/required-env")
def required_env(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    return {"agent": name, "required_env": _required_env_items(agent)}


@router.get("/agents/{name}/secrets")
def list_agent_secrets(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    required = {
        item["env_name"]: {
            "env_name": item["env_name"],
            "mode": item["mode"],
            "status": item["status"],
        }
        for item in _required_env_items(agent)
    }
    for slot in credential_slots.list_slots(agent):
        required.setdefault(
            slot.env_name,
            {
                "env_name": slot.env_name,
                "mode": slot.mode,
                "status": secret_store.status(agent.id, slot.env_name),
            },
        )
    return {"agent": name, "secrets": sorted(required.values(), key=lambda item: item["env_name"])}


@router.put("/agents/{name}/secrets/{env_name}")
def set_agent_secret(
    name: str,
    env_name: str,
    body: SecretWriteBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    if body.value == "":
        raise HTTPException(status_code=400, detail="empty value rejected; use delete to clear")
    credential_slots.ensure_slot(agent, f"env:{env_name}", mode="inject", env_name=env_name)
    try:
        secret_store.set(agent.id, env_name, body.value, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_log.write_audit(
        user.id,
        "agent.secret_set",
        target_type="agent",
        target_id=name,
        detail={"env_name": env_name},
    )
    return {"env_name": env_name, "status": secret_store.status(agent.id, env_name)}


@router.delete("/agents/{name}/secrets/{env_name}")
def delete_agent_secret(
    name: str,
    env_name: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    secret_store.delete(agent.id, env_name)
    audit_log.write_audit(
        user.id,
        "agent.secret_delete",
        target_type="agent",
        target_id=name,
        detail={"env_name": env_name},
    )
    return {"env_name": env_name, "status": secret_store.status(agent.id, env_name)}


def _required_env_items(agent: agent_store.Agent) -> list[dict[str, Any]]:
    slots_by_env = {slot.env_name: slot for slot in credential_slots.list_slots(agent)}
    sources: dict[str, str] = {}
    agent_file = agent_file_from_store(agent)
    for target in agent_file.models.targets:
        if target.api_key_env:
            sources.setdefault(target.api_key_env, "Models")
    for server in agent_file.mcp_servers:
        if server.api_key_env:
            sources.setdefault(server.api_key_env, "MCP")
        # env/headers values may reference a secret via the ``env:VAR`` prefix; the value
        # itself is a reference (not the secret), so the operator fills VAR on the Secrets tab.
        for mapping in (server.env, server.headers):
            for value in mapping.values():
                if isinstance(value, str) and value.startswith("env:"):
                    sources.setdefault(value[4:], "MCP")
    if agent_file.im.slack is not None:
        sources.setdefault(agent_file.im.slack.bot_token_env, "IM")
        sources.setdefault(agent_file.im.slack.app_token_env, "IM")

    items: list[dict[str, Any]] = []
    for env_name, source in sorted(sources.items()):
        slot = slots_by_env.get(env_name)
        items.append(
            {
                "env_name": env_name,
                "source": source,
                "mode": slot.mode if slot else "operator",
                "status": secret_store.status(agent.id, env_name),
            }
        )
    return items
