"""External git -> pool inbound sync (GitOps).

Mirrors an external git repo (authoritative) into the local skill pool: fetch + reset
--hard onto the remote branch head, re-materialize builtin seeds, then reconcile the admin
catalog (inbound audit gate: severe -> quarantine; recompute current_version; soft-delete
skills removed upstream). All git interaction stays platform-side; the sweep is bulkheaded
so a sync failure never aborts the scheduler, a webhook request, or boot.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fleetent.platform.skill_management import git_source_store, pool_git, skill_admin_store
from fleetent.skills import audit as skill_audit
from fleetent.skills import registry as skill_registry

logger = logging.getLogger(__name__)

_SYNC_AUTHOR = "system <system@fleetent>"


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _pool_dir() -> Path:
    return Path(skill_registry._resolve_skills_dir(None))


def _git_root(config: dict[str, Any]) -> Path:
    """Derive the git repo root from the scan root and configured ``skills_subdir``.

    ``_pool_dir()`` (``FLEETENT_SKILLS_DIR``) is always the scan root (R1 invariant);
    the git root is the scan root minus the ``skills_subdir`` suffix. Empty subdir
    degenerates to the scan root unchanged (flat, backward-compatible layout).
    """
    return pool_git.resolve_git_root(_pool_dir(), str(config.get("skills_subdir") or ""))


_secret_resolver: Callable[[int | None, str], str | None] | None = None


def set_secret_resolver(resolver: Callable[[int | None, str], str | None] | None) -> None:
    """Inject the credential resolver (platform wires secret_store.get_decrypted at boot).

    Keeps pool_sync off the agent_lifecycle face (plane boundary); unset -> no credentials.
    """
    global _secret_resolver
    _secret_resolver = resolver


def _secret(env_name: str | None) -> str | None:
    if not env_name or _secret_resolver is None:
        return None
    return _secret_resolver(None, env_name)


def is_sync_due(config: dict[str, Any] | None, *, now_iso: str) -> bool:
    """Whether a scheduled sync is due now (pure; drives the sweep)."""
    if config is None or not config.get("enabled"):
        return False
    interval = config.get("sync_interval_seconds")
    if not interval:
        return False
    last = config.get("last_sync_at")
    if not last:
        return True
    try:
        last_dt = datetime.datetime.fromisoformat(str(last))
        now_dt = datetime.datetime.fromisoformat(now_iso)
    except ValueError:
        return True
    return (now_dt - last_dt).total_seconds() >= float(interval)


def sync_external_git(*, trigger: str = "scheduled") -> dict[str, Any]:
    """Sync the pool from the configured external git source. Bulkheaded: never raises."""
    config = git_source_store.get_config()
    if config is None or not config.get("enabled") or not config.get("remote_url"):
        return {"skipped": True, "reason": "not configured"}
    try:
        return _do_sync(config, trigger)
    except Exception as exc:  # noqa: BLE001 — bulkhead: a sync failure must not propagate
        logger.warning("skill_git_sync_failed trigger=%s error=%s", trigger, exc, exc_info=True)
        git_source_store.record_sync(
            commit=config.get("last_synced_commit"), at=_now(), error=str(exc)
        )
        return {"error": str(exc)}


def _do_sync(config: dict[str, Any], trigger: str) -> dict[str, Any]:
    remote_url = str(config["remote_url"])
    branch = str(config.get("branch") or "main")
    username = _secret(config.get("username_env"))
    password = _secret(config.get("token_env"))
    # Git ops (init/fetch/reset) address the whole repo -> git root; skill scanning and
    # builtin re-seed FS writes stay on the scan root (FLEETENT_SKILLS_DIR).
    git_root = _git_root(config)
    subdir = str(config.get("skills_subdir") or "")

    pool_git.init_pool_with_remote(git_root, remote_url)
    remote_sha = pool_git.fetch_remote(
        git_root, remote_url=remote_url, branch=branch, username=username, password=password
    )
    if remote_sha == config.get("last_synced_commit"):
        # A manual "sync now" is also a "reconcile now": the operator may be recovering
        # catalog state that drifted (e.g. a skill left archived) even when the remote has
        # no new commit. Skip the heavy fetch/reset (the pool is already at this sha and
        # still carries its re-seeded builtins) but re-run the catalog reconcile + index
        # reload. Scheduled/webhook syncs keep the cheap no-op short-circuit.
        if trigger == "manual":
            _realign_status_only(_pool_dir())
            skill_registry.reload(str(_pool_dir()))
            git_source_store.record_sync(commit=remote_sha, at=_now(), error=None)
            return {"changed": False, "reconciled": True, "commit": remote_sha}
        git_source_store.record_sync(commit=remote_sha, at=_now(), error=None)
        return {"changed": False, "commit": remote_sha}

    pool_git.reset_pool_to(git_root, remote_sha)
    # Reconcile while HEAD == the fetched commit so per-skill versions resolve to the mirrored
    # remote commit (a later commit would shift HEAD and break version recompute).
    _reconcile_catalog_after_sync(_pool_dir(), git_root, subdir)
    # reset --hard drops builtin skills the external repo doesn't carry; re-seed + commit so they
    # stay distributable (builtins are scanned agent-side, not tracked in the admin catalog).
    # materialize_builtin_skills() writes to the scan root itself (R1); commit opens the Repo at
    # the git root with skill_name=None (stage all), so subdir must be passed to scope staging to
    # the skills subtree — otherwise a git root that coincides with FLEETENT_HOME (the common
    # skills_subdir layout) would sweep the platform's own runtime files into the pool repo.
    skill_registry.materialize_builtin_skills()
    pool_git.commit_pool(
        git_root, message="seed: re-materialize builtin skills", author=_SYNC_AUTHOR, subdir=subdir
    )
    # Refresh the in-memory index so registry-backed reads (admin content/description,
    # runtime skill lookup) see the mirrored skills. Without this the server keeps the
    # empty index it scanned at boot (before the first sync populated the pool): the list
    # endpoint still shows names via the DB catalog, but `registry.load` KeyErrors and the
    # admin UI renders blank content.
    skill_registry.reload(str(_pool_dir()))
    git_source_store.record_sync(commit=remote_sha, at=_now(), error=None)
    return {"changed": True, "commit": remote_sha}


def _reconcile_catalog_after_sync(scan_dir: Path, git_root: Path, subdir: str) -> None:
    """Inbound audit gate + version recompute + soft-delete of upstream-removed skills.

    Args:
        scan_dir: Skill scan root — only skills under it are enumerated (excludes sibling
            monorepo directories that the mirror carries but fleetent must not scan).
        git_root: Git repo root where ``.git`` lives; content/version reads open a ``Repo``
            here and resolve the ``<subdir>/<name>`` tree path.
        subdir: The ``skills_subdir`` prefix (``""`` when scan root == git root).
    """
    pool_skills = pool_git.list_pool_skills(scan_dir)
    skill_admin_store.ensure_catalog_entries(pool_skills)
    for name in pool_skills:
        content = pool_git.pool_content_at(git_root, name, "HEAD", subdir=subdir) or ""
        hits = skill_audit.audit(content, content)
        rules = sorted({h.rule_id for h in hits})
        if skill_audit.has_severe(hits):
            skill_admin_store.set_audit_result(name, "rejected", rules)
            skill_admin_store.set_status(name, "quarantined")
        else:
            skill_admin_store.set_audit_result(
                name, "suspicious" if hits else "pass", rules or None
            )
            skill_admin_store.set_status(name, "active")
            version = pool_git.pool_version_for_skill(git_root, name, subdir=subdir)
            skill_admin_store.set_current_version(name, version)
        skill_admin_store.set_source(name, "managed")

    pool_set = set(pool_skills)
    for state in skill_admin_store.list_states(include_archived=False):
        sname = str(state["skill_name"])
        if sname not in pool_set and state.get("status") == "active":
            skill_admin_store.set_status(sname, "archived")


def _realign_status_only(scan_dir: Path) -> None:
    """Cheap active/archived re-alignment for a manual sync when the remote sha is unchanged.

    The pool content is identical to the last full sync (same sha), so audit verdicts and
    per-skill versions cannot have changed — only local catalog *status* may have drifted
    (e.g. a skill manually archived). Revive archived skills the pool still carries and
    soft-delete active skills the pool no longer has, skipping the per-skill git blob reads
    and version walks a full reconcile does (those dominate the cost on a large mirror and
    made "sync now" hang for minutes). Quarantined skills are left untouched: a severe-audit
    verdict from the last full sync stands until the content actually changes.
    """
    pool_skills = pool_git.list_pool_skills(scan_dir)
    skill_admin_store.ensure_catalog_entries(pool_skills)
    pool_set = set(pool_skills)
    for name in pool_skills:
        if skill_admin_store.get_state(name)["status"] == "archived":
            skill_admin_store.set_status(name, "active")
    for state in skill_admin_store.list_states(include_archived=False):
        sname = str(state["skill_name"])
        if sname not in pool_set and state.get("status") == "active":
            skill_admin_store.set_status(sname, "archived")


def align_pool_to_remote(config: dict[str, Any] | None = None) -> str | None:
    """Fetch + reset the pool to the external branch head, returning the sha.

    Lightweight mirror used by the outbound backflow change after merging a PR (no audit /
    catalog reconcile here -- the next full ``sync_external_git`` handles that). Returns None
    if no external source is configured.
    """
    config = config or git_source_store.get_config()
    if config is None or not config.get("enabled") or not config.get("remote_url"):
        return None
    remote_url = str(config["remote_url"])
    branch = str(config.get("branch") or "main")
    git_root = _git_root(config)
    pool_git.init_pool_with_remote(git_root, remote_url)
    remote_sha = pool_git.fetch_remote(
        git_root,
        remote_url=remote_url,
        branch=branch,
        username=_secret(config.get("username_env")),
        password=_secret(config.get("token_env")),
    )
    pool_git.reset_pool_to(git_root, remote_sha)
    return remote_sha


def scheduled_sweep() -> dict[str, Any]:
    """Sweep entrypoint for the platform maintenance scheduler: sync if due."""
    config = git_source_store.get_config()
    if not is_sync_due(config, now_iso=_now()):
        return {"skipped": True, "reason": "not due"}
    return sync_external_git(trigger="scheduled")
