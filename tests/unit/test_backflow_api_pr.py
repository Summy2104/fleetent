"""Unit tests for backflow_api governance under GitOps (skill-backflow-git-pr).

When an external git source is enabled, accept/reject/fork operate via the PR lifecycle
(merge / close / fork-branch) and reuse pool_sync.align_pool_to_remote instead of writing
the pool directly. Git unavailability returns 503 without touching drift/epoch. The
endpoint functions are called directly with auth + stores patched (no TestClient).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from fleetent.integrations.git_platform import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
    GitPlatformUnavailableError,
    PullRequestRef,
)
from fleetent.platform.skill_management import (
    backflow_api,
    backflow_pr_sweep,
    backflow_store,
    git_source_store,
    pool_git,
    pool_sync,
    skill_admin_store,
)

_CONFIG = {"enabled": 1, "provider": "fake", "branch": "main", "branch_prefix": "backflow"}


class _FakeBackend(BaseGitPlatformBackend):
    name = "fake"
    capabilities = GitPlatformCapabilities(
        open_pr=True, merge_pr=True, close_pr=True, query_pr=True
    )

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.merged: list[str] = []
        self.closed: list[str] = []
        self.opened: list[dict] = []
        self.pushed: list[dict] = []

    def available(self) -> bool:
        return not self.unavailable

    def push_branch(self, *, branch, bundle, subdir, base_ref, message, author) -> str:
        if self.unavailable:
            raise GitPlatformUnavailableError("down")
        self.pushed.append({"branch": branch, "subdir": subdir})
        return f"sha-{branch}"

    def open_pull_request(
        self, *, source_branch, target_branch, title, description=""
    ) -> PullRequestRef:
        if self.unavailable:
            raise GitPlatformUnavailableError("down")
        self.opened.append({"source": source_branch, "target": target_branch})
        return PullRequestRef(
            pr_id="77", url="https://pr/77", state="open", source_branch=source_branch
        )

    def merge_pull_request(self, pr_id: str) -> PullRequestRef:
        if self.unavailable:
            raise GitPlatformUnavailableError("down")
        self.merged.append(pr_id)
        return PullRequestRef(
            pr_id=pr_id,
            url=f"https://pr/{pr_id}",
            state="merged",
            source_branch="backflow/7/crm-ops",
            merge_commit="mc123",
        )

    def close_pull_request(self, pr_id: str) -> PullRequestRef:
        if self.unavailable:
            raise GitPlatformUnavailableError("down")
        self.closed.append(pr_id)
        return PullRequestRef(
            pr_id=pr_id,
            url=f"https://pr/{pr_id}",
            state="closed",
            source_branch="backflow/7/crm-ops",
        )


@pytest.fixture
def gitops(monkeypatch):
    """Enable GitOps, inject a fake backend, and stub the pool-alignment + stores."""
    fake = _FakeBackend()
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(pool_sync, "align_pool_to_remote", MagicMock(return_value="head-sha"))
    monkeypatch.setattr(pool_git, "pool_version_for_skill", lambda _d, _n, **_kw: "newsha")
    monkeypatch.setattr(skill_admin_store, "set_current_version", MagicMock())
    monkeypatch.setattr(skill_admin_store, "set_drift", MagicMock())
    monkeypatch.setattr(skill_admin_store, "bump_resync_epoch", MagicMock())
    monkeypatch.setattr(skill_admin_store, "set_binding", MagicMock())
    monkeypatch.setattr(backflow_store, "set_status", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    return fake


def _proposal(**over):
    base = {
        "id": 1,
        "status": "pending",
        "agent_id": 7,
        "skill_name": "crm-ops",
        "proposed_bundle": {"SKILL.md": "x"},
        "conflict": 0,
        "pr_id": "42",
        "pr_branch": "backflow/7/crm-ops",
        "pr_state": "pr_open",
    }
    base.update(over)
    return base


def test_accept_merges_pr_aligns_pool_and_clears_drift(gitops, monkeypatch) -> None:
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    result = backflow_api.accept_proposal(1, None, "Session t", None)

    assert gitops.merged == ["42"]
    pool_sync.align_pool_to_remote.assert_called_once()
    skill_admin_store.set_current_version.assert_called_once_with("crm-ops", "newsha")
    skill_admin_store.set_drift.assert_called_once_with(7, "crm-ops", drifted=False)
    skill_admin_store.bump_resync_epoch.assert_called_once_with(7, "crm-ops")
    backflow_store.set_status.assert_called_once_with(1, "accepted", overridden_head=None)
    assert result["ok"] is True


def test_accept_git_unavailable_returns_503_without_touching_drift(gitops, monkeypatch) -> None:
    gitops.unavailable = True
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    with pytest.raises(HTTPException) as exc:
        backflow_api.accept_proposal(1, None, "Session t", None)

    assert exc.value.status_code == 503
    skill_admin_store.set_drift.assert_not_called()
    skill_admin_store.bump_resync_epoch.assert_not_called()
    pool_sync.align_pool_to_remote.assert_not_called()


def test_conflict_requires_confirm(gitops, monkeypatch) -> None:
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal(conflict=1))

    with pytest.raises(HTTPException) as exc:
        backflow_api.accept_proposal(1, None, "Session t", None)
    assert exc.value.status_code == 428
    assert gitops.merged == []


def test_reject_closes_pr_and_clears_drift(gitops, monkeypatch) -> None:
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    result = backflow_api.reject_proposal(1, "Session t")

    assert gitops.closed == ["42"]
    skill_admin_store.set_drift.assert_called_once_with(7, "crm-ops", drifted=False)
    skill_admin_store.bump_resync_epoch.assert_called_once_with(7, "crm-ops")
    backflow_store.set_status.assert_called_once_with(1, "rejected")
    assert result["ok"] is True


def test_fork_pushes_branch_merges_and_rebinds(gitops, monkeypatch) -> None:
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    result = backflow_api.fork_proposal(
        1, backflow_api.ForkBody(fork_name="crm-ops-support"), "Session t"
    )

    assert gitops.pushed and gitops.pushed[0]["subdir"] == "crm-ops-support"
    assert gitops.merged  # fork PR merged
    skill_admin_store.set_binding.assert_any_call(7, "crm-ops-support", True, updated_by="admin")
    backflow_store.set_status.assert_called_once_with(1, "forked", forked_as="crm-ops-support")
    assert result["forked_as"] == "crm-ops-support"


def test_fork_pushes_branch_with_skills_subdir_prefix(gitops, monkeypatch) -> None:
    """When skills_subdir is configured, the fork's push_branch subdir must be prefixed."""
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG_SUBDIR)
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    result = backflow_api.fork_proposal(
        1, backflow_api.ForkBody(fork_name="crm-ops-support"), "Session t"
    )

    assert gitops.pushed and gitops.pushed[0]["subdir"] == "skills/crm-ops-support"
    assert result["forked_as"] == "crm-ops-support"


def test_open_pr_endpoint_opens_for_backed_up(gitops, monkeypatch) -> None:
    monkeypatch.setattr(
        backflow_store, "get_proposal", lambda _i: _proposal(pr_id=None, pr_state="backed_up")
    )

    result = backflow_api.open_pr_proposal(1, "Session t")

    assert gitops.opened == [{"source": "backflow/7/crm-ops", "target": "main"}]
    backflow_store.set_pr_state.assert_any_call(1, "pr_open")
    assert result["ok"] is True


def test_sync_backflow_endpoint_triggers_sweep(monkeypatch) -> None:
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    ran = MagicMock(return_value={"backed_up": 1, "prs_opened": 0})
    monkeypatch.setattr(backflow_pr_sweep, "run_now", ran)

    result = backflow_api.sync_backflow("Session t")

    ran.assert_called_once()
    assert result["backed_up"] == 1


# --- skills_subdir threading (skill-backflow-git-pr task 7) --------------------

_CONFIG_SUBDIR = {**_CONFIG, "skills_subdir": "skills"}


def test_accept_threads_subdir_into_pool_version_lookup(gitops, monkeypatch) -> None:
    """When skills_subdir is set, _accept_via_pr must pass subdir= to pool_version_for_skill."""
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG_SUBDIR)
    version = MagicMock(return_value="newsha")
    monkeypatch.setattr(pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    backflow_api.accept_proposal(1, None, "Session t", None)

    assert version.call_args.kwargs.get("subdir") == "skills"
    assert version.call_args.args[1] == "crm-ops"


def test_accept_defaults_subdir_empty_without_config(gitops, monkeypatch) -> None:
    """Without skills_subdir configured, subdir defaults to '' (baseline behaviour)."""
    version = MagicMock(return_value="newsha")
    monkeypatch.setattr(pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    backflow_api.accept_proposal(1, None, "Session t", None)

    assert version.call_args.kwargs.get("subdir") == ""


def test_accept_conflict_override_lookup_also_threads_subdir(gitops, monkeypatch) -> None:
    """The conflict overridden_head lookup must also carry subdir=."""
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG_SUBDIR)
    version = MagicMock(return_value="newsha")
    monkeypatch.setattr(pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal(conflict=1))

    backflow_api.accept_proposal(1, None, "Session t", "true")  # X-Confirm: true

    for call in version.call_args_list:
        assert call.kwargs.get("subdir") == "skills"


def test_fork_threads_subdir_into_pool_version_lookup(gitops, monkeypatch) -> None:
    """_fork_via_pr must pass subdir= when looking up the forked skill's new version."""
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG_SUBDIR)
    version = MagicMock(return_value="newsha")
    monkeypatch.setattr(pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(backflow_store, "get_proposal", lambda _i: _proposal())

    backflow_api.fork_proposal(1, backflow_api.ForkBody(fork_name="crm-ops-support"), "Session t")

    assert version.call_args.kwargs.get("subdir") == "skills"
    assert version.call_args.args[1] == "crm-ops-support"
    # push_branch's own subdir kwarg is the tree path (task 8): skills_subdir-prefixed.
    assert gitops.pushed and gitops.pushed[0]["subdir"] == "skills/crm-ops-support"


def test_get_backflow_diff_passes_scan_root_git_root_and_subdir(monkeypatch) -> None:
    """get_backflow_diff must derive git_root/subdir and pass all three to the store."""
    from pathlib import Path

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
    from pathlib import Path

    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(git_source_store, "get_config", lambda: None)
    monkeypatch.setattr(backflow_api, "_pool_dir", lambda: Path("/scan"))
    monkeypatch.setattr(pool_git, "resolve_git_root", lambda d, _s: d)
    captured = MagicMock(return_value={"diff_vs_base": "", "diff_vs_head": "", "conflict": False})
    monkeypatch.setattr(backflow_store, "get_proposal_diff", captured)

    backflow_api.get_backflow_diff(1, "Session t")

    assert captured.call_args.kwargs["pool_dir"] == Path("/scan")
    assert captured.call_args.kwargs["git_root"] == Path("/scan")
    assert captured.call_args.kwargs["subdir"] == ""
