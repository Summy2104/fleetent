"""Unit tests for backflow_api governance under GitOps.

When an external git source is enabled the platform never writes toward the authority
branch: accept and fork are disabled (409 — the operator opens a PR from the pushed
backup branch in the git host UI), reject stays local (clear drift + bump epoch so the
node reverts to the pool head), and the diff endpoint remains available. Endpoint
functions are called directly with auth + stores patched (no TestClient).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from fleetent.platform.skill_management import (
    backflow_api,
    backflow_pr_sweep,
    backflow_store,
    git_source_store,
    pool_git,
    skill_admin_store,
)

_CONFIG = {"enabled": 1, "provider": "bitbucket", "branch": "main", "branch_prefix": "backflow"}
_CONFIG_SUBDIR = {**_CONFIG, "skills_subdir": "skills"}


def _proposal(**over):
    base = {
        "id": 1,
        "status": "pending",
        "agent_id": 7,
        "skill_name": "crm-ops",
        "proposed_bundle": {"SKILL.md": "x"},
        "conflict": 0,
        "pr_branch": "backflow/7/crm-ops",
        "pr_state": "backed_up",
    }
    base.update(over)
    return base


@pytest.fixture
def gitops(monkeypatch):
    """Enable GitOps + patch admin auth and stores. No git backend is needed: the
    accept/reject/fork endpoints perform no git writes under GitOps anymore."""
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(skill_admin_store, "set_drift", MagicMock())
    monkeypatch.setattr(skill_admin_store, "bump_resync_epoch", MagicMock())
    monkeypatch.setattr(backflow_store, "set_status", MagicMock())


def test_accept_disabled_under_gitops(gitops, monkeypatch) -> None:
    """Accept is the human's job (open a PR on the backup branch); platform returns 409
    and touches no drift/status."""
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    with pytest.raises(HTTPException) as exc:
        backflow_api.accept_proposal(1, None, "Session t", None)

    assert exc.value.status_code == 409
    skill_admin_store.set_drift.assert_not_called()
    backflow_store.set_status.assert_not_called()


def test_accept_conflict_also_disabled_under_gitops(gitops, monkeypatch) -> None:
    """Even a conflict proposal returns 409 (not 428): GitOps accept is disabled outright."""
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal(conflict=1))

    with pytest.raises(HTTPException) as exc:
        backflow_api.accept_proposal(1, None, "Session t", "true")

    assert exc.value.status_code == 409


def test_fork_disabled_under_gitops(gitops, monkeypatch) -> None:
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    with pytest.raises(HTTPException) as exc:
        backflow_api.fork_proposal(
            1, backflow_api.ForkBody(fork_name="crm-ops-support"), "Session t"
        )

    assert exc.value.status_code == 409
    backflow_store.set_status.assert_not_called()


def test_reject_clears_drift_locally_under_gitops(gitops, monkeypatch) -> None:
    """Reject stays local: clear drift + bump epoch so the node reverts its home copy to the
    (unchanged) pool head. No PR is touched — the platform performs no git writes."""
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    result = backflow_api.reject_proposal(1, "Session t")

    skill_admin_store.set_drift.assert_called_once_with(7, "crm-ops", drifted=False)
    skill_admin_store.bump_resync_epoch.assert_called_once_with(7, "crm-ops")
    backflow_store.set_status.assert_called_once_with(1, "rejected")
    assert result["ok"] is True


def test_open_pr_endpoint_is_gone() -> None:
    """The manual open-PR endpoint was removed (platform never opens PRs)."""
    assert not hasattr(backflow_api, "open_pr_proposal")
    routes = {getattr(r, "path", "") for r in backflow_api.router.routes}
    assert not any(path.endswith("/open-pr") for path in routes)


def test_sync_backflow_endpoint_triggers_sweep(monkeypatch) -> None:
    """The manual 'sync backflow' still triggers a sweep — pushing backup branches only."""
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    ran = MagicMock(return_value={"backed_up": 1})
    monkeypatch.setattr(backflow_pr_sweep, "run_now", ran)

    result = backflow_api.sync_backflow("Session t")

    ran.assert_called_once()
    assert result["backed_up"] == 1


def test_get_backflow_diff_passes_scan_root_git_root_and_subdir(monkeypatch) -> None:
    """get_backflow_diff must derive git_root/subdir and pass all three to the store."""
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG_SUBDIR)
    monkeypatch.setattr(backflow_api, "_pool_dir", lambda: Path("/scan/skills"))
    monkeypatch.setattr(pool_git, "resolve_git_root", lambda _d, _s: Path("/scan"))
    captured = MagicMock(return_value={"diff_vs_base": "", "diff_vs_head": "", "conflict": False})
    monkeypatch.setattr(backflow_store, "get_proposal_diff", captured)

    backflow_api.get_backflow_diff(1, "Session t")

    assert captured.call_args.kwargs["pool_dir"] == Path("/scan/skills")
    assert captured.call_args.kwargs["git_root"] == Path("/scan")
    assert captured.call_args.kwargs["subdir"] == "skills"


def test_get_backflow_diff_defaults_subdir_empty_without_config(monkeypatch) -> None:
    """Without a config row, subdir='' and git_root == scan root (baseline)."""
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(git_source_store, "get_config", lambda: None)
    monkeypatch.setattr(backflow_api, "_pool_dir", lambda: Path("/scan"))
    monkeypatch.setattr(pool_git, "resolve_git_root", lambda d, _s: d)
    captured = MagicMock(return_value={"diff_vs_base": "", "diff_vs_head": "", "conflict": False})
    monkeypatch.setattr(backflow_store, "get_proposal_diff", captured)

    backflow_api.get_backflow_diff(1, "Session t")

    assert captured.call_args.kwargs["pool_dir"] == Path("/scan")
    assert captured.call_args.kwargs["git_root"] == Path("/scan")
