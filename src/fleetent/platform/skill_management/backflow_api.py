"""FastAPI router for /admin/skills/backflow — backflow governance decisions.

Exposes three decision endpoints (accept / reject / fork) for skill backflow
proposals. All writes require admin auth; no DM/agent path touches these.

Auth mirrors skill_admin_api: ``Authorization: Session <token>``.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import agent_store, auth, user_store
from fleetent.platform.skill_management import backflow_store, skill_admin_store
from fleetent.platform.skill_management.pool_git import commit_pool
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin/skills/backflow")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}


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


def _write_bundle_atomic(skill_dir: Path, bundle: dict[str, str]) -> None:
    tmp_parent = skill_dir.parent / ".tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"{skill_dir.name}-", dir=tmp_parent))
    backup_dir = skill_dir.with_name(f"{skill_dir.name}.bak")
    try:
        for relpath, content in bundle.items():
            dest = tmp_dir / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if skill_dir.exists():
            skill_dir.rename(backup_dir)
        tmp_dir.rename(skill_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if backup_dir.exists() and not skill_dir.exists():
            backup_dir.rename(skill_dir)
        raise


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
    """Return the dual diff (vs base / vs head) for a backflow proposal (admin-only)."""
    _require_admin(authorization)
    try:
        return backflow_store.get_proposal_diff(proposal_id, pool_dir=_pool_dir())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- decision endpoints -------------------------------------------------------


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
    proposed_bundle: dict[str, str] = row["proposed_bundle"]
    pool_dir = _pool_dir()

    # Record what we're overriding if this is a conflict accept
    overridden_head: str | None = None
    if row["conflict"]:
        from fleetent.platform.skill_management.pool_git import pool_version_for_skill

        overridden_head = pool_version_for_skill(pool_dir, skill_name)

    # Write evolved bundle to pool
    skill_dir = pool_dir / skill_name
    _write_bundle_atomic(skill_dir, proposed_bundle)

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

    # Clear drift and signal the owning node to re-sync its home copy to the new pool
    # head; otherwise the node keeps reporting drift and re-nomination loops forever.
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)

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

    # Reject discards the local evolution: clear drift and signal the owning node to
    # re-sync its home copy back to the (unchanged) pool head, reverting the edit.
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)

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
    proposed_bundle: dict[str, str] = row["proposed_bundle"]
    pool_dir = _pool_dir()

    fork_name = body.fork_name
    if not fork_name:
        raise HTTPException(status_code=422, detail="fork_name is required")

    # Write fork to pool (original skill dir untouched)
    fork_dir = pool_dir / fork_name
    _write_bundle_atomic(fork_dir, proposed_bundle)

    # Commit fork to pool git
    new_sha = commit_pool(
        pool_dir,
        message=f"backflow fork: {skill_name} → {fork_name}",
        author=body.author,
        skill_name=fork_name,
    )
    if new_sha is not None:
        skill_admin_store.set_current_version(fork_name, new_sha)

    # Rebind the source agent to the fork and clear drift on the original binding.
    skill_admin_store.set_binding(agent_id, skill_name, False, updated_by=user.name)
    skill_admin_store.set_binding(agent_id, fork_name, True, updated_by=user.name)
    # The fork became a new skill; revert the original on the node and clear its drift.
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)

    # Close proposal
    backflow_store.set_status(proposal_id, "forked", forked_as=fork_name)

    return {"ok": True, "proposal_id": proposal_id, "forked_as": fork_name, "user": user.name}
