"""Outbound backflow PR sweep (skill-backflow-git-pr).

A platform-side periodic task (analogous to kb_connector_sweep) that turns pending
backflow proposals into git pull requests, in two bulkheaded passes:

1. Back up: push one aggregate backup branch per agent ``<branch_prefix>/<agent>`` carrying
   all that agent's drifted skills (never the authority branch) -- immediate safekeeping so
   the agent's edits survive, and a single human PR adopts the whole set.
2. Adoption is a human PR from the backup branch to the authority branch -- the platform
   never opens or merges PRs.

Every git operation is bulkheaded: a ``GitPlatformUnavailableError`` marks the proposal
``deferred`` for the next round and never crashes the sweep. The nominate / node path
stays git-free -- git lives only here and in the governance endpoints.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fleetent import agent_store
from fleetent.integrations.git_platform import (
    BaseGitPlatformBackend,
    GitPlatformConfig,
    GitPlatformUnavailableError,
    create_git_platform,
)
from fleetent.platform.skill_management import (
    backflow_store,
    git_source_store,
    skill_admin_store,
)
from fleetent.skills import registry as skill_registry
from fleetent.structured_logging import get_logger

_logger = get_logger("skill_management.backflow_pr_sweep")

_PUSH_AUTHOR = "fleetent <backflow@fleetent>"

# Per-round budgets keep one sweep's wall-clock bounded (the rest are picked up next round),
# so a huge backlog can't make a single round run for many minutes. Nomination pulls a bundle
# over HTTP; backup pushes a branch — both are network-bound.
_NOMINATE_BUDGET_PER_ROUND = 50
_BACKUP_BUDGET_PER_ROUND = 50

# Injection seams (mirroring pool_sync): the secret resolver decrypts credential env-name
# references; the backend factory is overridable in tests. Both default to production wiring.
_secret_resolver: Callable[[int | None, str], str | None] | None = None
_backend_factory: Callable[[dict[str, Any]], BaseGitPlatformBackend] | None = None


def set_secret_resolver(resolver: Callable[[int | None, str], str | None] | None) -> None:
    global _secret_resolver
    _secret_resolver = resolver


def set_backend_factory(
    factory: Callable[[dict[str, Any]], BaseGitPlatformBackend] | None,
) -> None:
    global _backend_factory
    _backend_factory = factory


def _secret(env_name: str | None) -> str | None:
    if not env_name or _secret_resolver is None:
        return None
    return _secret_resolver(None, env_name)


def _build_backend(config: dict[str, Any]) -> BaseGitPlatformBackend:
    if _backend_factory is not None:
        return _backend_factory(config)
    gp_config = GitPlatformConfig(
        provider=str(config.get("provider", "bitbucket")),
        remote_url=str(config.get("remote_url", "")),
        branch=str(config.get("branch", "main")),
        branch_prefix=str(config.get("branch_prefix", "backflow")),
        auto_open_pr=bool(config.get("auto_open_pr")),
        base_url=config.get("base_url"),
        project=config.get("project"),
        repo=config.get("repo"),
        username=_secret(config.get("username_env")),
        token=_secret(config.get("token_env")),
    )
    return create_git_platform(config=gp_config)


def _safe_ref_component(text: str) -> str:
    """Sanitize a string into one legal git ref path component.

    Collapses every run of characters git forbids in a ref (space, ``~^:?*[\\``, ``/``,
    ``#`` …) to a single ``-`` and strips leading/trailing ``.``/``-``. Returns ``""`` if
    nothing legal remains, so callers can fall back to a stable id.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")


def _branch_name(config: dict[str, Any], agent_id: int) -> str:
    prefix = str(config.get("branch_prefix", "backflow"))
    # One aggregate branch per agent (all its drifted skills). Prefer the agent's human name
    # (sanitized); fall back to the numeric id when the agent is gone or its name has no legal
    # ref characters left.
    agent = agent_store.get_by_id(int(agent_id))
    component = _safe_ref_component(agent.name) if agent is not None else ""
    if not component:
        component = str(agent_id)
    return f"{prefix}/{component}"


def _back_up(backend: BaseGitPlatformBackend, config: dict[str, Any]) -> int:
    """Push one aggregate backup branch per agent (all its drifted skills). Returns #pushed.

    Snapshot-rebuild: each round rebuilds ``<prefix>/<agent>`` off the authority branch with
    that agent's full set of not-yet-landed drifted skills, so the branch — and the human PR
    off it — always reflects current drift. Landed proposals (pool already equals the evolved
    copy, i.e. the PR was merged and synced back) are marked ``merged`` and drop off. To avoid
    churning an open PR with an identical snapshot, an agent is re-pushed only when its set
    changed: a new/deferred proposal appeared, or a previously-included skill just landed.
    """
    pool_dir = Path(skill_registry._resolve_skills_dir(None))
    base_ref = str(config.get("branch", "main"))
    subdir = str(config.get("skills_subdir") or "")
    candidates = (
        backflow_store.list_by_pr_state(None)
        + backflow_store.list_by_pr_state("deferred")
        + backflow_store.list_by_pr_state("backed_up")
    )
    by_agent: dict[int, list[dict[str, Any]]] = {}
    shrank: set[int] = set()  # agents whose branch set lost a skill this round (needs rebuild)
    for proposal in candidates:
        agent_id = int(proposal["agent_id"])
        try:
            landed = backflow_store.is_landed(proposal, pool_dir)
        except Exception as exc:  # best-effort: a failed check must not block backing up
            _logger.warn(
                "backflow_landed_check_failed", proposal_id=int(proposal["id"]), exception=exc
            )
            landed = False
        if landed:
            backflow_store.set_pr_state(int(proposal["id"]), "merged")
            shrank.add(agent_id)
            continue
        by_agent.setdefault(agent_id, []).append(proposal)

    backed = 0
    for agent_id, group in by_agent.items():
        if backed >= _BACKUP_BUDGET_PER_ROUND:
            _logger.info("backflow_backup_budget_reached", budget=_BACKUP_BUDGET_PER_ROUND)
            break
        branch = _branch_name(config, agent_id)
        # Re-push when the agent's skill set changed (a new/deferred proposal, or an included
        # skill just landed) OR when a recorded backup branch predates the current naming scheme
        # (legacy per-skill "<prefix>/<agent>/<skill>" left over before the aggregate
        # "<prefix>/<agent>" migration): the aggregate branch was never created for such an agent,
        # so an unchanged-set skip would strand it forever. Skipping is only safe when the set is
        # unchanged AND every recorded branch already equals `branch` — otherwise a re-push would
        # merely churn an existing identical snapshot.
        stale_branch = any(
            p.get("pr_branch") is not None and p.get("pr_branch") != branch for p in group
        )
        needs_push = (
            agent_id in shrank
            or any(p.get("pr_state") in (None, "deferred") for p in group)
            or stale_branch
        )
        if not needs_push:
            continue
        # Combined bundle across the agent's drifted skills, keyed "<skill>/<relpath>".
        bundle: dict[str, str] = {}
        for proposal in group:
            skill = str(proposal["skill_name"])
            for rel, content in proposal["proposed_bundle"].items():
                bundle[f"{skill}/{rel}"] = content
        ids = [int(p["id"]) for p in group]
        try:
            backend.push_branch(
                branch=branch,
                bundle=bundle,
                subdir=subdir,
                base_ref=base_ref,
                message=f"backflow: {len(group)} skill(s) from agent {agent_id}",
                author=_PUSH_AUTHOR,
            )
        except GitPlatformUnavailableError as exc:
            _logger.warn("backflow_backup_deferred", agent_id=agent_id, exception=exc)
            for pid in ids:
                backflow_store.defer_pr_state(pid)
            continue
        except Exception as exc:  # bulkhead: one agent's failure never stops the rest
            _logger.error("backflow_backup_failed", agent_id=agent_id, exception=exc)
            continue
        for pid in ids:
            backflow_store.set_pr_link(pid, branch=branch)
            backflow_store.set_pr_state(pid, "backed_up")
        backed += 1
    return backed


def _nominate_drifted() -> int:
    """Nominate backflow proposals for drifted skills that don't have one yet.

    Runs in the (background) sweep rather than the node status-ingestion request path:
    each nomination pulls the evolved bundle from the owning node over HTTP, which must not
    block ``POST /nodes/{id}/status``. Bounded per round; bulkheaded per skill.
    """
    pool_dir = Path(skill_registry._resolve_skills_dir(None))
    nominated = 0
    for agent_id, skill_name in skill_admin_store.list_drifted():
        if nominated >= _NOMINATE_BUDGET_PER_ROUND:
            _logger.info("backflow_nominate_budget_reached", budget=_NOMINATE_BUDGET_PER_ROUND)
            break
        try:
            if backflow_store.nominate_if_absent(
                agent_id=agent_id, skill_name=skill_name, pool_dir=pool_dir
            ):
                nominated += 1
        except Exception as exc:  # bulkhead: one skill's capture failure never stops the rest
            _logger.warn(
                "backflow_auto_nominate_failed",
                agent_id=agent_id,
                skill=skill_name,
                exception=exc,
            )
    return nominated


def sweep() -> dict[str, Any]:
    """Run one backflow sweep round (bulkheaded; never raises).

    Two passes: (1) nominate proposals for drifted skills (captures the evolved bundle off
    the request path); (2) push one aggregate backup branch per agent (``<prefix>/<agent>``)
    for safekeeping. Opening a PR from a backup branch to the authority branch — any write to
    the authority branch — is deliberately the human's job in the git host; the platform
    never opens or merges PRs.
    """
    try:
        # Nomination records proposals + captures bundles; it does NOT touch git, so it runs
        # regardless of whether an external git source is enabled.
        nominated = _nominate_drifted()
        config = git_source_store.get_config()
        if not config or not config.get("enabled"):
            return {"nominated": nominated, "backed_up": 0, "skipped": "disabled"}
        backend = _build_backend(config)
        backed_up = _back_up(backend, config)
        return {"nominated": nominated, "backed_up": backed_up}
    except Exception as exc:  # outermost bulkhead: a sweep failure must not crash the scheduler
        _logger.error("backflow_pr_sweep_failed", exception=exc)
        return {"backed_up": 0, "error": str(exc)}


def run_now() -> dict[str, Any]:
    """Admin-triggered immediate sweep."""
    return sweep()
