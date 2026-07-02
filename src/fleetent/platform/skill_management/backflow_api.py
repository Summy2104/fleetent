"""FastAPI router for /admin/skills/backflow — read-only views + manual sweep.

Backflow governance is deliberately hands-off on the platform. An agent's home-side skill
edit is captured as a proposal (its evolved bundle) and pushed to a backup branch by
``backflow_pr_sweep``; the platform never decides accept / reject / fork and never writes
toward the authority branch. Adoption is entirely a human action in the git host: open a PR
from the backup branch to the authority branch and it flows back on the next inbound sync.

This module therefore exposes only read views (list proposals + dual diff) and a manual
"sweep now" trigger. Auth mirrors skill_admin_api (``Authorization: Session <token>``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from fleetent import agent_store, auth, user_store
from fleetent.platform.skill_management import (
    backflow_pr_sweep,
    backflow_store,
    git_source_store,
    pool_git,
)
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin/skills/backflow")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}


# --- injectable seam (pool directory) ----------------------------------------


def engine_skills_dir() -> str:
    """The writable user skills directory (pool root)."""
    return skill_registry._resolve_skills_dir(None)


def _pool_dir() -> Path:
    return Path(engine_skills_dir())


# --- auth helpers -------------------------------------------------------------


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
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


# --- read endpoints -----------------------------------------------------------


@router.get("")
def list_backflow_proposals(
    status: str = "pending",
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """List backflow proposals (admin-only); excludes the full ``proposed_bundle``."""
    _require_admin(authorization)
    items: list[dict[str, Any]] = []
    for proposal in backflow_store.list_proposals(status=status):
        item = {key: value for key, value in proposal.items() if key != "proposed_bundle"}
        agent = agent_store.get_by_id(proposal["agent_id"])
        item["agent_name"] = agent.name if agent is not None else None
        items.append(item)
    return items


@router.get("/{proposal_id}/diff")
def get_backflow_diff(
    proposal_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return the dual diff (vs base / vs head) for a backflow proposal (admin-only).

    The scan root (``_pool_dir()``) is used for on-disk reads while the git root +
    ``skills_subdir`` reconstruct the base bundle from git.
    """
    _require_admin(authorization)
    config = git_source_store.get_config()
    subdir = (config.get("skills_subdir") or "") if config is not None else ""
    pool_dir = _pool_dir()
    git_root = pool_git.resolve_git_root(pool_dir, subdir)
    try:
        return backflow_store.get_proposal_diff(
            proposal_id, pool_dir=pool_dir, git_root=git_root, subdir=subdir
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- manual sweep -------------------------------------------------------------


@router.post("/sync-backflow")
def sync_backflow(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Manually trigger one backflow sweep round (admin-only): pushes backup branches only,
    never opens a PR."""
    _require_admin(authorization)
    return backflow_pr_sweep.run_now()
