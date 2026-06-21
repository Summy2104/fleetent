"""FastAPI router for the agents idempotent apply API (askit fleetent target).

askit's fleetent deployer does not write SQLite directly — it POSTs compiled agent
definitions here and fleetent upserts them, so fleetent stays the sole writer of its
own DB. Apply owns only the agent *definition* (name immutable; system_prompt /
allowed_tools / model mutable). Bindings (user_agents) are runtime
state and are never overwritten by apply.

Provenance is tracked in agent_admin_store: applied agents become managed (spec_owned);
applying onto an existing adhoc agent "adopts" it (same agent_id, flipped to managed),
so history and bindings carry over without a rebuild. Never imports the agent loop.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent.platform.agent_management_console import agent_admin_store

router = APIRouter(prefix="/admin/agents")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable agent_store seams ---------------------------------------------


def get_agent_def(name: str) -> dict[str, Any] | None:
    """Resolve an agent definition (id/system_prompt/allowed_tools). Bridges agent_store."""
    return None


def create_agent_def(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    model_overrides: dict[str, Any] | None = None,
) -> int:
    """Create a new agent definition; returns its id. Bridges agent_store.create_agent."""
    return 0


def update_agent_def(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    model_overrides: dict[str, Any] | None = None,
) -> None:
    """Update mutable fields of an existing agent. Bridges agent_store."""
    return None


def _require_admin(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


class AgentSpec(BaseModel):
    name: str
    system_prompt: str
    allowed_tools: list[str] = []
    model_overrides: dict[str, Any] | None = None


class BatchBody(BaseModel):
    agents: list[AgentSpec]


def _apply_one(spec: AgentSpec, actor_id: str) -> dict[str, Any]:
    existing = get_agent_def(spec.name)
    if existing is None:
        agent_id = create_agent_def(
            spec.name,
            spec.system_prompt,
            spec.allowed_tools,
            spec.model_overrides,
        )
        action = "created"
    else:
        # name is immutable (it is the key); only mutable fields are updated. bindings untouched.
        update_agent_def(
            spec.name,
            spec.system_prompt,
            spec.allowed_tools,
            spec.model_overrides,
        )
        agent_id = int(existing["id"])
        was_adhoc = agent_admin_store.get_state(agent_id)["provenance"] == "adhoc"
        action = "adopted" if was_adhoc else "updated"
    agent_admin_store.set_provenance(agent_id, "managed")  # managed == spec_owned
    return {"name": spec.name, "agent_id": agent_id, "action": action, "provenance": "managed"}


@router.post("/apply")
def apply(spec: AgentSpec, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = _apply_one(spec, user.id)
    audit_log.write_audit(user.id, "agent.apply", "agent", spec.name, detail=result)
    return result


@router.post("/apply:batch")
def apply_batch(body: BatchBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    results = [_apply_one(spec, user.id) for spec in body.agents]
    audit_log.write_audit(
        user.id, "agent.apply_batch", "agent", None, detail={"count": len(results)}
    )
    return {"applied": results}
