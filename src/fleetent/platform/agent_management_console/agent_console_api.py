"""FastAPI router for /admin/agents — the Agent management console (lifecycle face).

Layers the operational management face on top of the agent definition/binding store:
enable/disable, archive (soft delete) with binding protection + restore, clone,
the read-only template library, managed/adhoc provenance + drift, and the per-agent
observation view.

Agent CRUD/versioning and the binding tables come from agent_store; per-agent metric
aggregation comes from observability. Those are reached through injectable seams
(mockable in tests). Lifecycle status / provenance / drift are persisted in
agent_admin_store. Never imports the agent loop.

Auth: reads allow viewer+admin, writes require admin; archive needs X-Confirm.
"""

from typing import Any

import yaml
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.governance import audit_log
from fleetent.platform.agent_management_console import (
    agent_admin_store,
    agent_observability,
    agent_template_store,
)

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable seams (agent_store / observability) ---------------------------


def get_agent_def(name: str) -> dict[str, Any] | None:
    """Resolve an agent's active definition.

    Returns id/system_prompt/allowed_tools plus the per-version config fields
    skills_dir/mcp_server_ids/model_overrides/memory_namespace.
    """
    return None


def create_agent_def(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    skills_dir: str | None = None,
    mcp_server_ids: list[str] | None = None,
    model_overrides: dict[str, Any] | None = None,
    memory_namespace: str = "default",
    template_id: str | None = None,
    plugins: list[str] | None = None,
    features: dict[str, Any] | None = None,
    icon: str | None = None,
) -> None:
    """Create a new agent definition (no bindings). Bridges agent_store.create_agent."""
    return None


def set_agent_icon(name: str, icon: str | None) -> None:
    """Set an agent's avatar emoji (agent-level). Bridges agent_store.set_icon."""
    return None


def agent_icons() -> dict[str, str]:
    """Map of agent name -> icon. Bridges agent_store.icons_by_name (for the list view)."""
    return {}


def update_agent_def(
    name: str,
    system_prompt: str | None,
    allowed_tools: list[str] | None,
    skills_dir: str | None = None,
    mcp_server_ids: list[str] | None = None,
    model_overrides: dict[str, Any] | None = None,
    memory_namespace: str | None = None,
) -> None:
    """Edit an agent by snapshotting a new active version. Bridges create_version.

    ``None`` fields are left unchanged (inherited from the prior active version).
    """
    return None


def delete_agent_def(name: str) -> bool:
    """Hard-delete an agent definition. Bridges agent_store.delete_agent."""
    return False


def references_for(agent_name: str) -> dict[str, Any]:
    """Who references an agent (users/channels) — drives archive protection."""
    agent = get_agent_def(agent_name)
    if agent is None:
        return {"users": [], "channels": []}
    return agent_admin_store.references(int(agent["id"]))


def agent_observability_agg(agent_name: str, window: str) -> dict[str, Any]:
    """Per-agent aggregation (calls/tokens/cost/error-rate/latency/approvals).

    Delegates to the read-only observability roll-up; kept as a seam so tests can mock it.
    """
    return agent_observability.aggregate(agent_name, window)


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


class CloneBody(BaseModel):
    new_name: str


class CreateBody(BaseModel):
    name: str
    template_id: str
    system_prompt: str = ""
    allowed_tools: list[str] = []
    plugins: list[str] = []
    features: dict[str, Any] = {}
    skills_dir: str | None = None
    mcp_server_ids: list[str] | None = None
    model_overrides: dict[str, Any] = {}
    memory_namespace: str = "default"
    icon: str | None = None
    # Optional raw capabilities block (allowed_tools/plugins/features) pasted as YAML;
    # parsed server-side and, when present, overrides the structured fields above.
    capabilities_yaml: str | None = None


class UpdateBody(BaseModel):
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    skills_dir: str | None = None
    mcp_server_ids: list[str] | None = None
    model_overrides: dict[str, Any] | None = None
    memory_namespace: str | None = None
    icon: str | None = None


# --- templates (literal path before /{name}) ----------------------------------


class TemplateCreateBody(BaseModel):
    id: str
    display_name: str
    allowed_tools: list[str] = []
    system_prompt: str = ""


class TemplateUpdateBody(BaseModel):
    display_name: str | None = None
    allowed_tools: list[str] | None = None
    system_prompt: str | None = None


@router.get("/agent-templates")
def list_templates(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return agent_template_store.list_templates()


@router.post("/agent-templates", status_code=201)
def create_template(
    body: TemplateCreateBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if not body.id.strip():
        raise HTTPException(status_code=422, detail="id required")
    if agent_template_store.get_template(body.id) is not None:
        raise HTTPException(status_code=409, detail="template already exists")
    template = agent_template_store.create_template(
        body.id, body.display_name, body.allowed_tools, body.system_prompt
    )
    audit_log.write_audit(user.id, "template.create", "agent_template", body.id)
    return template


@router.patch("/agent-templates/{template_id}")
def update_template(
    template_id: str, body: TemplateUpdateBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    kwargs: dict[str, Any] = {}
    if body.display_name is not None:
        kwargs["display_name"] = body.display_name
    if body.allowed_tools is not None:
        kwargs["allowed_tools"] = body.allowed_tools
    if body.system_prompt is not None:
        kwargs["system_prompt"] = body.system_prompt
    template = agent_template_store.update_template(template_id, **kwargs)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    audit_log.write_audit(user.id, "template.update", "agent_template", template_id)
    return template


@router.delete("/agent-templates/{template_id}")
def delete_template(template_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if not agent_template_store.delete_template(template_id):
        raise HTTPException(status_code=404, detail="template not found")
    audit_log.write_audit(user.id, "template.delete", "agent_template", template_id)
    return {"id": template_id, "deleted": True}


# --- list ---------------------------------------------------------------------


@router.get("/agents")
def list_agents(
    include_archived: bool = False, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    rows = agent_admin_store.list_states(include_archived=include_archived)
    # Icon enrichment is cosmetic — never let it break the list if the lookup fails.
    try:
        icons = agent_icons()
    except Exception:  # noqa: BLE001 — best-effort avatar lookup
        icons = {}
    for r in rows:
        r["icon"] = icons.get(str(r.get("agent_name") or ""))
    return rows


@router.get("/agents/{name}/observability")
def observability(
    name: str, window: str = "7d", authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    return agent_observability_agg(name, window)


# --- CRUD: create / read-full / update / delete -------------------------------


def _def_response(name: str) -> dict[str, Any]:
    agent = get_agent_def(name)
    state = agent_admin_store.get_state(name)
    out: dict[str, Any] = {
        "agent": name,
        "provenance": state["provenance"],
        "status": state["status"],
    }
    if agent is not None:
        out["system_prompt"] = agent["system_prompt"]
        out["allowed_tools"] = agent["allowed_tools"]
        out["plugins"] = agent.get("plugins", [])
        out["features"] = agent.get("features", {})
        out["skills_dir"] = agent.get("skills_dir")
        out["mcp_server_ids"] = agent.get("mcp_server_ids")
        out["model_overrides"] = agent.get("model_overrides", {})
        out["memory_namespace"] = agent.get("memory_namespace", "default")
        out["template_id"] = agent.get("template_id")
        out["icon"] = agent.get("icon")
    return out


def _resolve_capabilities(body: CreateBody) -> tuple[list[str], list[str], dict[str, Any]]:
    """Resolve allowed_tools/plugins/features, letting a pasted YAML block override them.

    The YAML is recorded as-is: whatever keys it carries replace the structured fields.
    """
    allowed_tools, plugins, features = body.allowed_tools, body.plugins, body.features
    if body.capabilities_yaml and body.capabilities_yaml.strip():
        try:
            parsed = yaml.safe_load(body.capabilities_yaml)
        except yaml.YAMLError as exc:
            raise HTTPException(
                status_code=422, detail=f"invalid capabilities YAML: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail="capabilities YAML must be a mapping")
        allowed_tools = parsed.get("allowed_tools", allowed_tools)
        plugins = parsed.get("plugins", plugins)
        features = parsed.get("features", features)
    return allowed_tools, plugins, features


@router.post("/agents", status_code=201)
def create_agent(body: CreateBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if get_agent_def(body.name) is not None:
        raise HTTPException(status_code=409, detail="agent already exists")
    if agent_template_store.get_template(body.template_id) is None:
        raise HTTPException(status_code=404, detail="template not found")
    allowed_tools, plugins, features = _resolve_capabilities(body)
    create_agent_def(
        body.name,
        body.system_prompt,
        allowed_tools,
        body.skills_dir,
        body.mcp_server_ids,
        body.model_overrides,
        body.memory_namespace,
        body.template_id,
        plugins=plugins,
        features=features,
        icon=body.icon,
    )
    agent_admin_store.set_provenance(body.name, "adhoc")
    agent_admin_store.enable(body.name)
    audit_log.write_audit(user.id, "agent.create", "agent", body.name)
    return _def_response(body.name)


@router.get("/agents/{name}")
def get_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = get_agent_def(name)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _def_response(name)


@router.patch("/agents/{name}")
def update_agent(
    name: str, body: UpdateBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if get_agent_def(name) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    update_agent_def(
        name,
        body.system_prompt,
        body.allowed_tools,
        body.skills_dir,
        body.mcp_server_ids,
        body.model_overrides,
        body.memory_namespace,
    )
    if body.icon is not None:
        set_agent_icon(name, body.icon)
    agent_admin_store.mark_drift(name)  # no-op unless provenance is managed
    audit_log.write_audit(user.id, "agent.update", "agent", name)
    return _def_response(name)


@router.delete("/agents/{name}")
def delete_agent(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if get_agent_def(name) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    refs = references_for(name)
    if refs["users"] or refs["channels"]:
        raise HTTPException(status_code=409, detail={"error": "agent still bound", **refs})
    _require_confirm(x_confirm)
    delete_agent_def(name)
    agent_admin_store.delete_state(name)
    audit_log.write_audit(user.id, "agent.delete", "agent", name)
    return {"agent": name, "deleted": True}


# --- lifecycle ----------------------------------------------------------------


@router.post("/agents/{name}/enable")
def enable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.enable(name)
    audit_log.write_audit(user.id, "agent.enable", "agent", name)
    return {"agent": name, "status": "enabled"}


@router.post("/agents/{name}/disable")
def disable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.disable(name)
    audit_log.write_audit(user.id, "agent.disable", "agent", name)
    return {"agent": name, "status": "disabled"}


@router.post("/agents/{name}/archive")
def archive_agent(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    refs = references_for(name)
    if refs["users"] or refs["channels"]:
        raise HTTPException(status_code=409, detail={"error": "agent still bound", **refs})
    _require_confirm(x_confirm)
    agent_admin_store.archive(name)
    audit_log.write_audit(user.id, "agent.archive", "agent", name)
    return {"agent": name, "status": "archived"}


@router.post("/agents/{name}/restore")
def restore_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.restore(name)
    audit_log.write_audit(user.id, "agent.restore", "agent", name)
    return {"agent": name, "status": "enabled"}


# --- clone --------------------------------------------------------------------


@router.post("/agents/{name}/clone")
def clone_agent(
    name: str, body: CloneBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    src = get_agent_def(name)
    if src is None:
        raise HTTPException(status_code=404, detail="source agent not found")
    if get_agent_def(body.new_name) is not None:
        raise HTTPException(status_code=409, detail="target name already exists")
    create_agent_def(
        body.new_name,
        src["system_prompt"],
        src["allowed_tools"],
        src.get("skills_dir"),
        src.get("mcp_server_ids"),
        src.get("model_overrides", {}),
        src.get("memory_namespace", "default"),
    )
    # clone is a fresh adhoc agent with no bindings and default enabled status
    agent_admin_store.set_provenance(body.new_name, "adhoc")
    agent_admin_store.enable(body.new_name)
    audit_log.write_audit(user.id, "agent.clone", "agent", body.new_name, detail={"source": name})
    return {"agent": body.new_name, "cloned_from": name, "provenance": "adhoc"}
