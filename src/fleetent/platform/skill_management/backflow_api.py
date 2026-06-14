"""FastAPI router for /admin/skills/backflow — backflow governance decisions.

Exposes three decision endpoints (accept / reject / fork) for skill backflow
proposals. All writes require admin auth; no DM/agent path touches these.

Auth mirrors skill_admin_api: ``Authorization: Session <token>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.platform.skill_management import backflow_store, skill_admin_store
from fleetent.platform.skill_management.pool_git import commit_pool
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin/skills/backflow")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable seam (pool directory) ----------------------------------------


def engine_skills_dir() -> str:
    """The writable user skills directory (pool root)."""
    return skill_registry._resolve_skills_dir(None)


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


# --- request bodies -----------------------------------------------------------


class AcceptBody(BaseModel):
    author: str = "admin <admin@fleetent>"


class ForkBody(BaseModel):
    fork_name: str
    author: str = "admin <admin@fleetent>"


# --- helpers ------------------------------------------------------------------


def _get_proposal_or_404(proposal_id: int) -> dict[str, Any]:
    row = backflow_store.get_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
    return row


def _pool_dir() -> Path:
    return Path(engine_skills_dir())


# --- endpoints ----------------------------------------------------------------


@router.post("/{proposal_id}/accept")
def accept_proposal(
    proposal_id: int,
    body: AcceptBody | None = None,
    authorization: str | None = Header(default=None),
    x_confirm: str | None = Header(default=None),
) -> dict[str, Any]:
    """Accept a backflow proposal: write evolved content to pool and commit.

    If the proposal has conflict=1 (pool advanced past base_version), the caller
    must supply ``X-Confirm: true`` to acknowledge the overwrite.
    """
    user = _require_admin(authorization)
    if body is None:
        body = AcceptBody()
    row = _get_proposal_or_404(proposal_id)

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {row['status']!r}")

    if row["conflict"] and x_confirm != "true":
        raise HTTPException(
            status_code=428,
            detail="conflict: pool has advanced; supply X-Confirm: true to override",
        )

    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    proposed_content: str = row["proposed_content"]
    pool_dir = _pool_dir()

    # Record what we're overriding if this is a conflict accept
    overridden_head: str | None = None
    if row["conflict"]:
        from fleetent.platform.skill_management.pool_git import pool_version_for_skill

        overridden_head = pool_version_for_skill(pool_dir, skill_name)

    # Write evolved content to pool
    skill_dir = pool_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(proposed_content, encoding="utf-8")

    # Commit to pool git
    new_sha = commit_pool(
        pool_dir,
        message=f"backflow accept: {skill_name}",
        author=body.author,
        skill_name=skill_name,
    )

    # Advance current_version
    if new_sha is not None:
        skill_admin_store.set_current_version(skill_name, new_sha)

    # Clear drift for the source agent
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)

    # Close proposal; record overridden_head if conflict
    backflow_store.set_status(proposal_id, "accepted", overridden_head=overridden_head)

    return {"ok": True, "proposal_id": proposal_id, "new_version": new_sha, "user": user.name}


@router.post("/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Reject a backflow proposal: pool unchanged, drift cleared, proposal closed."""
    user = _require_admin(authorization)
    row = _get_proposal_or_404(proposal_id)

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {row['status']!r}")

    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]

    # Clear drift so next materialize will overwrite the evolved home copy
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)

    # Close proposal
    backflow_store.set_status(proposal_id, "rejected")

    return {"ok": True, "proposal_id": proposal_id, "user": user.name}


@router.post("/{proposal_id}/fork")
def fork_proposal(
    proposal_id: int,
    body: ForkBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Fork a backflow: create a new named skill in pool; original skill unchanged."""
    user = _require_admin(authorization)
    row = _get_proposal_or_404(proposal_id)

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {row['status']!r}")

    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    proposed_content: str = row["proposed_content"]
    pool_dir = _pool_dir()

    fork_name = body.fork_name
    if not fork_name:
        raise HTTPException(status_code=422, detail="fork_name is required")

    # Write fork to pool (original skill dir untouched)
    fork_dir = pool_dir / fork_name
    fork_dir.mkdir(parents=True, exist_ok=True)
    (fork_dir / "SKILL.md").write_text(proposed_content, encoding="utf-8")

    # Commit fork to pool git
    commit_pool(
        pool_dir,
        message=f"backflow fork: {skill_name} → {fork_name}",
        author=body.author,
        skill_name=fork_name,
    )

    # Clear drift for the source agent
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)

    # Close proposal
    backflow_store.set_status(proposal_id, "forked", forked_as=fork_name)

    return {"ok": True, "proposal_id": proposal_id, "forked_as": fork_name, "user": user.name}
