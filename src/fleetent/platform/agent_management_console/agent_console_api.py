"""FastAPI router for /admin/agents — the Agent management console (lifecycle face).

Layers the operational management face on top of the agent definition/binding store:
enable/disable, archive (soft delete) with binding protection + restore, clone,
managed/adhoc provenance + drift, and the per-agent
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

from fleetent import audit_log, auth, user_store
from fleetent.platform.agent_management_console import (
    agent_admin_store,
    agent_observability,
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
    plugins: list[str] | None = None,
    features: dict[str, Any] | None = None,
    icon: str | None = None,
    tenant_id: str = "default",
    team_id: str | None = None,
    config_overrides: dict[str, Any] | None = None,
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
    tenant_id: str | None = None,
    team_id: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> None:
    """Edit an agent by snapshotting a new active version. Bridges create_version.

    ``None`` fields are left unchanged (inherited from the prior active version).
    """
    return None


def delete_agent_def(name: str) -> bool:
    """Hard-delete an agent definition. Bridges agent_store.delete_agent."""
    return False


rename_agent_def: None = None  # removed — agent name is immutable after creation


def references_for(agent_name: str) -> dict[str, Any]:
    """Who references an agent (users/channels) — drives archive protection."""
    agent = get_agent_def(agent_name)
    if agent is None:
        return {"users": [], "channels": []}
    return agent_admin_store.references(int(agent["id"]))


def _require_agent_id(name: str) -> int:
    agent = get_agent_def(name)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return int(agent["id"])


def agent_observability_agg(agent_name: str, window: str) -> dict[str, Any]:
    """Per-agent aggregation (calls/tokens/cost/error-rate/latency/approvals).

    Delegates to the read-only observability roll-up; kept as a seam so tests can mock it.
    """
    return agent_observability.aggregate(agent_name, window)


# --- injectable seams (node_management read-only projections) -----------------
# Wired in server.py to node_store / placement_store. Default no-ops so the console
# degrades to desired-state-only (and unit tests can mock them) when unwired.


def get_agent_runtime(agent_id: int) -> dict[str, Any] | None:
    """Last reported actual state for one agent. Bridges node_store.get_agent_status."""
    return None


def get_agent_placement(agent_id: int) -> dict[str, Any] | None:
    """The agent's node placement, or None if unpinned. Bridges placement_store.get_for_agent."""
    return None


def list_agent_runtimes() -> list[dict[str, Any]]:
    """All agents' reported actual state. Bridges node_store.list_agent_status (list view)."""
    return []


def list_agent_placements() -> list[dict[str, Any]]:
    """All agent→node placements. Bridges placement_store.list_placements (list view)."""
    return []


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
    tenant_id: str = "default"
    team_id: str | None = None
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
    # Optional Advanced overrides: any agent.yaml field (governance/deployment/intelligence/
    # access/…) as YAML or JSON, deep-merged onto the materialized defaults.
    config_overrides_yaml: str | None = None
    # Structured overrides from the discrete Advanced-settings inputs; deep-merged over the
    # YAML block (so the curated fields win over the long-tail text).
    config_overrides_fields: dict[str, Any] = {}


class UpdateBody(BaseModel):
    tenant_id: str | None = None
    team_id: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    skills_dir: str | None = None
    mcp_server_ids: list[str] | None = None
    model_overrides: dict[str, Any] | None = None
    memory_namespace: str | None = None
    icon: str | None = None
    # Optional capabilities YAML (parsed server-side); when present its allowed_tools
    # override the structured field, mirroring create.
    capabilities_yaml: str | None = None
    config_overrides_yaml: str | None = None  # Advanced agent.yaml overrides (YAML/JSON)
    config_overrides_fields: dict[str, Any] | None = None  # discrete Advanced-settings inputs


# --- list ---------------------------------------------------------------------


def _runtime_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project a node_agent_status row to the response shape, or None when unreported."""
    if row is None:
        return None
    return {
        "phase": row.get("phase"),
        "health": row.get("health"),
        "pid": row.get("pid"),
        "node_id": row.get("node_id"),
        "reported_at": row.get("reported_at"),
    }


def _placement_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project an agent_placements row to the response shape, or None when unpinned."""
    if row is None:
        return None
    return {
        "node_id": row.get("node_id"),
        "pinned_at": row.get("pinned_at"),
        "pinned_by": row.get("pinned_by"),
    }


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
    # Batch the dual-state projection (one read each) and join by agent_id — no N+1.
    runtimes = {r["agent_id"]: r for r in list_agent_runtimes()}
    placements = {r["agent_id"]: r for r in list_agent_placements()}
    for r in rows:
        agent_id = r.get("agent_id")
        r["icon"] = icons.get(str(r.get("agent_name") or ""))
        r["runtime"] = _runtime_view(runtimes.get(agent_id))
        r["placement"] = _placement_view(placements.get(agent_id))
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
    agent_id = None if agent is None else int(agent["id"])
    state = (
        {
            "agent_id": None,
            "agent_name": name,
            "status": "enabled",
            "provenance": "adhoc",
        }
        if agent_id is None
        else agent_admin_store.get_state(agent_id)
    )
    out: dict[str, Any] = {
        "agent": name,
        "provenance": state["provenance"],
        "status": state["status"],
        "runtime": _runtime_view(get_agent_runtime(agent_id)) if agent_id is not None else None,
        "placement": (
            _placement_view(get_agent_placement(agent_id)) if agent_id is not None else None
        ),
    }
    if agent is not None:
        out["version"] = agent.get("version", 1)
        out["tenant_id"] = agent.get("tenant_id", "default")
        out["team_id"] = agent.get("team_id")
        out["system_prompt"] = agent["system_prompt"]
        out["allowed_tools"] = agent["allowed_tools"]
        out["plugins"] = agent.get("plugins", [])
        out["features"] = agent.get("features", {})
        out["skills_dir"] = agent.get("skills_dir")
        out["mcp_server_ids"] = agent.get("mcp_server_ids")
        out["model_overrides"] = agent.get("model_overrides", {})
        out["memory_namespace"] = agent.get("memory_namespace", "default")
        out["icon"] = agent.get("icon")
        out["config_overrides"] = agent.get("config_overrides", {})
    return out


def _resolve_capabilities(
    allowed_tools: list[str],
    plugins: list[str],
    features: dict[str, Any],
    capabilities_yaml: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Resolve allowed_tools/plugins/features, letting a pasted YAML block override them.

    The YAML is recorded as-is: whatever keys it carries replace the structured fields.
    """
    if capabilities_yaml and capabilities_yaml.strip():
        try:
            parsed = yaml.safe_load(capabilities_yaml)
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


def _parse_overrides_yaml(text: str | None) -> dict[str, Any]:
    """Parse the Advanced overrides box (YAML or JSON) into a dict; blank -> {}."""
    if not text or not text.strip():
        return {}
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"invalid overrides YAML: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="overrides must be a YAML/JSON mapping")
    return parsed


def _merge_overrides(yaml_text: str | None, fields: dict[str, Any] | None) -> dict[str, Any]:
    """Combine the long-tail YAML box with the discrete Advanced-settings fields.

    Curated discrete fields win, deep-merged over the YAML block.
    """

    def deep(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
        out = dict(base)
        for key, value in over.items():
            out[key] = (
                deep(out[key], value)
                if isinstance(value, dict) and isinstance(out.get(key), dict)
                else value
            )
        return out

    return deep(_parse_overrides_yaml(yaml_text), fields or {})


@router.post("/agents", status_code=201)
def create_agent(body: CreateBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if get_agent_def(body.name) is not None:
        raise HTTPException(status_code=409, detail="agent already exists")
    allowed_tools, plugins, features = _resolve_capabilities(
        body.allowed_tools, body.plugins, body.features, body.capabilities_yaml
    )
    create_agent_def(
        body.name,
        body.system_prompt,
        allowed_tools,
        body.skills_dir,
        body.mcp_server_ids,
        body.model_overrides,
        body.memory_namespace,
        plugins=plugins,
        features=features,
        icon=body.icon,
        tenant_id=body.tenant_id,
        team_id=body.team_id,
        config_overrides=_merge_overrides(body.config_overrides_yaml, body.config_overrides_fields),
    )
    agent_id = _require_agent_id(body.name)
    agent_admin_store.set_provenance(agent_id, "adhoc")
    # New agents start disabled: not yet pinned to a node, so "enabled" would be a
    # promise no node can keep (desired-state pull filters on status == enabled).
    agent_admin_store.disable(agent_id)
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
    target_id = _require_agent_id(name)
    target = name
    allowed_tools = body.allowed_tools
    if body.capabilities_yaml is not None:
        # Capabilities YAML drives allowed_tools; plugins/features are inherited unchanged.
        allowed_tools, _, _ = _resolve_capabilities([], [], {}, body.capabilities_yaml)
    # Only forward identity fields the caller explicitly set, so a partial update can't
    # null an unmentioned team_id (None here is a real value: clear it).
    identity: dict[str, Any] = {}
    if "tenant_id" in body.model_fields_set:
        identity["tenant_id"] = body.tenant_id
    if "team_id" in body.model_fields_set:
        identity["team_id"] = body.team_id
    if (
        "config_overrides_yaml" in body.model_fields_set
        or "config_overrides_fields" in body.model_fields_set
    ):
        identity["config_overrides"] = _merge_overrides(
            body.config_overrides_yaml, body.config_overrides_fields
        )
    update_agent_def(
        target,
        body.system_prompt,
        allowed_tools,
        body.skills_dir,
        body.mcp_server_ids,
        body.model_overrides,
        body.memory_namespace,
        **identity,
    )
    if body.icon is not None:
        set_agent_icon(target, body.icon)
    agent_admin_store.mark_drift(target_id)  # no-op unless provenance is managed
    audit_log.write_audit(user.id, "agent.update", "agent", target)
    return _def_response(target)


@router.delete("/agents/{name}")
def delete_agent(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_id = _require_agent_id(name)
    refs = references_for(name)
    if refs["users"] or refs["channels"]:
        raise HTTPException(status_code=409, detail={"error": "agent still bound", **refs})
    _require_confirm(x_confirm)
    delete_agent_def(name)
    agent_admin_store.delete_state(agent_id)
    audit_log.write_audit(user.id, "agent.delete", "agent", name)
    return {"agent": name, "deleted": True}


# --- lifecycle ----------------------------------------------------------------


@router.post("/agents/{name}/enable")
def enable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_id = _require_agent_id(name)
    # Enabling an agent that no node hosts is a no-op promise: gate on node placement.
    if get_agent_placement(agent_id) is None:
        raise HTTPException(status_code=409, detail="agent not bound to a node")
    agent_admin_store.enable(agent_id)
    audit_log.write_audit(user.id, "agent.enable", "agent", name)
    return {"agent": name, "status": "enabled"}


@router.post("/agents/{name}/disable")
def disable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.disable(_require_agent_id(name))
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
    agent_admin_store.archive(_require_agent_id(name))
    audit_log.write_audit(user.id, "agent.archive", "agent", name)
    return {"agent": name, "status": "archived"}


@router.post("/agents/{name}/restore")
def restore_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.restore(_require_agent_id(name))
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
    # clone is a fresh adhoc agent with no bindings; starts disabled (not pinned yet)
    agent_id = _require_agent_id(body.new_name)
    agent_admin_store.set_provenance(agent_id, "adhoc")
    agent_admin_store.disable(agent_id)
    audit_log.write_audit(user.id, "agent.clone", "agent", body.new_name, detail={"source": name})
    return {"agent": body.new_name, "cloned_from": name, "provenance": "adhoc"}
