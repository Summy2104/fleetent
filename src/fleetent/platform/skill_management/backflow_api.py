"""FastAPI router for /admin/skills/backflow — backflow governance decisions.

Decision endpoints (accept / reject / fork) plus manual open-pr / sync-backflow. All
writes require admin auth; no DM/agent path touches these. Auth mirrors skill_admin_api
(``Authorization: Session <token>``).

Two modes: when an external git source is enabled (GitOps), decisions operate via the PR
lifecycle (merge / close / fork-branch) and reuse ``pool_sync.align_pool_to_remote`` rather
than writing the pool directly -- a direct pool write would be discarded by the next
inbound reset. When no external source is configured, the legacy direct-write path runs
unchanged. All git interaction stays platform-side; git unavailability returns 503 without
mutating drift / resync_epoch.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import agent_store, auth, user_store
from fleetent.integrations.git_platform import GitPlatformUnavailableError
from fleetent.platform.skill_management import (
    backflow_pr_sweep,
    backflow_store,
    git_source_store,
    pool_git,
    pool_sync,
    skill_admin_store,
)
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin/skills/backflow")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_PUSH_AUTHOR = "fleetent <backflow@fleetent>"


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


def _git_root(config: dict[str, Any]) -> Path:
    """Return the pool's git root given an enabled GitOps ``config``.

    ``_pool_dir()`` is the skill *scan* root; when ``skills_subdir`` is configured the
    git root (where ``.git`` lives) is its parent. Used only by the GitOps-PR paths,
    which are reached only when ``config`` is confirmed enabled — the legacy direct-write
    paths keep using ``_pool_dir()`` (scan root == git root) untouched.
    """
    return pool_git.resolve_git_root(_pool_dir(), str(config.get("skills_subdir") or ""))


def _gitops_config() -> dict[str, Any] | None:
    """Return the external git source config when GitOps is enabled, else None."""
    config = git_source_store.get_config()
    return config if config and config.get("enabled") else None


def _ensure_pr(backend: Any, row: dict[str, Any], config: dict[str, Any]) -> str:
    """Return the proposal's PR id, opening one from its backup branch if needed."""
    if row.get("pr_id"):
        return str(row["pr_id"])
    branch = row.get("pr_branch")
    if not branch:
        raise HTTPException(
            status_code=409,
            detail="proposal not backed up yet; run the backflow sweep first",
        )
    target = str(config.get("branch", "main"))
    ref = backend.open_pull_request(
        source_branch=branch,
        target_branch=target,
        title=f"Backflow: {row['skill_name']} from agent {row['agent_id']}",
    )
    backflow_store.set_pr_link(
        int(row["id"]), pr_id=ref.pr_id, pr_url=ref.url, pr_target_branch=target
    )
    backflow_store.set_pr_state(int(row["id"]), "pr_open")
    return str(ref.pr_id)


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
    """Return the dual diff (vs base / vs head) for a backflow proposal (admin-only).

    Runs regardless of GitOps mode. The scan root (``_pool_dir()``) is used for on-disk
    reads while the git root + ``skills_subdir`` reconstruct the base bundle from git.
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


# --- GitOps (PR-based) decision paths -----------------------------------------


def _accept_via_pr(
    row: dict[str, Any], config: dict[str, Any], user: user_store.User
) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    backend = backflow_pr_sweep._build_backend(config)
    git_root = _git_root(config)
    subdir = str(config.get("skills_subdir") or "")

    overridden_head: str | None = None
    if row["conflict"]:
        overridden_head = pool_git.pool_version_for_skill(git_root, skill_name, subdir=subdir)

    try:
        pr_id = _ensure_pr(backend, row, config)
        ref = backend.merge_pull_request(pr_id)
    except GitPlatformUnavailableError as exc:
        backflow_store.set_pr_state(proposal_id, "deferred")
        raise HTTPException(status_code=503, detail=f"git platform unavailable: {exc}") from exc

    # Reuse the inbound alignment: fetch + reset the pool to the merged authority branch,
    # so the pool mirrors main rather than carrying a divergent direct write.
    pool_sync.align_pool_to_remote(config)
    new_sha = pool_git.pool_version_for_skill(git_root, skill_name, subdir=subdir)
    if new_sha is not None:
        skill_admin_store.set_current_version(skill_name, new_sha)
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)

    backflow_store.set_pr_link(proposal_id, pr_merge_commit=ref.merge_commit)
    backflow_store.set_pr_state(proposal_id, "merged")
    backflow_store.set_status(proposal_id, "accepted", overridden_head=overridden_head)
    return {"ok": True, "proposal_id": proposal_id, "new_version": new_sha, "user": user.name}


def _reject_via_pr(
    row: dict[str, Any], config: dict[str, Any], user: user_store.User
) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    pr_id = row.get("pr_id")
    if pr_id:
        backend = backflow_pr_sweep._build_backend(config)
        try:
            backend.close_pull_request(str(pr_id))
        except GitPlatformUnavailableError as exc:
            backflow_store.set_pr_state(proposal_id, "deferred")
            raise HTTPException(status_code=503, detail=f"git platform unavailable: {exc}") from exc
        backflow_store.set_pr_state(proposal_id, "closed")

    # Pool unchanged; the backup branch (if any) is kept for traceability. Clear drift and
    # bump the epoch so the node reverts its home copy to the (unchanged) pool head.
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)
    backflow_store.set_status(proposal_id, "rejected")
    return {"ok": True, "proposal_id": proposal_id, "user": user.name}


def _fork_via_pr(
    row: dict[str, Any], config: dict[str, Any], user: user_store.User, fork_name: str
) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    bundle: dict[str, str] = row["proposed_bundle"]
    backend = backflow_pr_sweep._build_backend(config)
    git_root = _git_root(config)
    subdir = str(config.get("skills_subdir") or "")
    target = str(config.get("branch", "main"))
    prefix = str(config.get("branch_prefix", "backflow"))
    fork_branch = f"{prefix}-fork/{agent_id}/{fork_name}"

    try:
        backend.push_branch(
            branch=fork_branch,
            bundle=bundle,
            subdir=pool_git._skill_tree_path(subdir, fork_name),
            base_ref=target,
            message=f"backflow fork: {skill_name} -> {fork_name}",
            author=_PUSH_AUTHOR,
        )
        ref = backend.open_pull_request(
            source_branch=fork_branch, target_branch=target, title=f"Backflow fork: {fork_name}"
        )
        backend.merge_pull_request(ref.pr_id)
    except GitPlatformUnavailableError as exc:
        backflow_store.set_pr_state(proposal_id, "deferred")
        raise HTTPException(status_code=503, detail=f"git platform unavailable: {exc}") from exc

    pool_sync.align_pool_to_remote(config)
    new_sha = pool_git.pool_version_for_skill(git_root, fork_name, subdir=subdir)
    if new_sha is not None:
        skill_admin_store.set_current_version(fork_name, new_sha)
    skill_admin_store.set_binding(agent_id, skill_name, False, updated_by=user.name)
    skill_admin_store.set_binding(agent_id, fork_name, True, updated_by=user.name)
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)
    backflow_store.set_status(proposal_id, "forked", forked_as=fork_name)
    return {"ok": True, "proposal_id": proposal_id, "forked_as": fork_name, "user": user.name}


# --- legacy (direct-write) decision paths -------------------------------------


def _accept_legacy(row: dict[str, Any], body: AcceptBody, user: user_store.User) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    proposed_bundle: dict[str, str] = row["proposed_bundle"]
    pool_dir = _pool_dir()

    overridden_head: str | None = None
    if row["conflict"]:
        overridden_head = pool_git.pool_version_for_skill(pool_dir, skill_name)

    _write_bundle_atomic(pool_dir / skill_name, proposed_bundle)
    new_sha = pool_git.commit_pool(
        pool_dir,
        message=f"backflow accept: {skill_name}",
        author=body.author,
        skill_name=skill_name,
    )
    if new_sha is not None:
        skill_admin_store.set_current_version(skill_name, new_sha)
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)
    backflow_store.set_status(proposal_id, "accepted", overridden_head=overridden_head)
    return {"ok": True, "proposal_id": proposal_id, "new_version": new_sha, "user": user.name}


def _reject_legacy(row: dict[str, Any], user: user_store.User) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_admin_store.set_drift(row["agent_id"], row["skill_name"], drifted=False)
    skill_admin_store.bump_resync_epoch(row["agent_id"], row["skill_name"])
    backflow_store.set_status(proposal_id, "rejected")
    return {"ok": True, "proposal_id": proposal_id, "user": user.name}


def _fork_legacy(
    row: dict[str, Any], body: ForkBody, user: user_store.User, fork_name: str
) -> dict[str, Any]:
    proposal_id = int(row["id"])
    skill_name: str = row["skill_name"]
    agent_id: int = row["agent_id"]
    proposed_bundle: dict[str, str] = row["proposed_bundle"]
    pool_dir = _pool_dir()

    _write_bundle_atomic(pool_dir / fork_name, proposed_bundle)
    new_sha = pool_git.commit_pool(
        pool_dir,
        message=f"backflow fork: {skill_name} → {fork_name}",
        author=body.author,
        skill_name=fork_name,
    )
    if new_sha is not None:
        skill_admin_store.set_current_version(fork_name, new_sha)
    skill_admin_store.set_binding(agent_id, skill_name, False, updated_by=user.name)
    skill_admin_store.set_binding(agent_id, fork_name, True, updated_by=user.name)
    skill_admin_store.set_drift(agent_id, skill_name, drifted=False)
    skill_admin_store.bump_resync_epoch(agent_id, skill_name)
    backflow_store.set_status(proposal_id, "forked", forked_as=fork_name)
    return {"ok": True, "proposal_id": proposal_id, "forked_as": fork_name, "user": user.name}


# --- decision endpoints -------------------------------------------------------


@router.post("/{proposal_id}/accept")
def accept_proposal(
    proposal_id: int,
    body: AcceptBody | None = None,
    authorization: str | None = Header(default=None),
    x_confirm: str | None = Header(default=None),
) -> dict[str, Any]:
    """Accept a backflow proposal (GitOps: merge PR + align pool; legacy: write pool).

    If the proposal has conflict=1 (pool advanced past base_version), the caller must
    supply ``X-Confirm: true`` to acknowledge the overwrite.
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
    config = _gitops_config()
    if config is not None:
        return _accept_via_pr(row, config, user)
    return _accept_legacy(row, body, user)


@router.post("/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Reject a backflow proposal (GitOps: close PR; legacy: no-op pool); pool unchanged."""
    user = _require_admin(authorization)
    row = _get_proposal_or_404(proposal_id)
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {row['status']!r}")
    config = _gitops_config()
    if config is not None:
        return _reject_via_pr(row, config, user)
    return _reject_legacy(row, user)


@router.post("/{proposal_id}/fork")
def fork_proposal(
    proposal_id: int,
    body: ForkBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Fork a backflow into a new named skill; original skill unchanged."""
    user = _require_admin(authorization)
    row = _get_proposal_or_404(proposal_id)
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {row['status']!r}")
    fork_name = body.fork_name
    if not fork_name:
        raise HTTPException(status_code=422, detail="fork_name is required")
    config = _gitops_config()
    if config is not None:
        return _fork_via_pr(row, config, user, fork_name)
    return _fork_legacy(row, body, user, fork_name)


@router.post("/{proposal_id}/open-pr")
def open_pr_proposal(
    proposal_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Manually open a PR for a backed-up proposal (GitOps only)."""
    user = _require_admin(authorization)
    row = _get_proposal_or_404(proposal_id)
    config = _gitops_config()
    if config is None:
        raise HTTPException(status_code=409, detail="external git source not enabled")
    backend = backflow_pr_sweep._build_backend(config)
    try:
        pr_id = _ensure_pr(backend, row, config)
    except GitPlatformUnavailableError as exc:
        backflow_store.set_pr_state(proposal_id, "deferred")
        raise HTTPException(status_code=503, detail=f"git platform unavailable: {exc}") from exc
    return {"ok": True, "proposal_id": proposal_id, "pr_id": pr_id, "user": user.name}


@router.post("/sync-backflow")
def sync_backflow(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Manually trigger one backflow sweep round (admin-only)."""
    _require_admin(authorization)
    return backflow_pr_sweep.run_now()
