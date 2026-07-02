"""Unit tests for backflow_api — read-only views + manual sweep (no platform governance).

Backflow governance is hands-off on the platform: an agent's edit is captured as a proposal
and pushed to a backup branch by the sweep; the platform never accepts/rejects/forks. This
module exposes only read views (list + dual diff) and a manual "sweep now" trigger. Adoption
is a human action in the git host. Endpoint functions are called directly with auth + stores
patched (no TestClient).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from fleetent.platform.skill_management import (
    backflow_api,
    backflow_pr_sweep,
    backflow_store,
    git_source_store,
    pool_git,
)

_CONFIG_SUBDIR = {
    "enabled": 1,
    "provider": "bitbucket",
    "branch": "main",
    "skills_subdir": "skills",
}


def test_governance_endpoints_are_removed() -> None:
    """accept / reject / fork / open-pr are gone — the platform never writes toward the
    authority branch and does not adopt/reject on the operator's behalf."""
    for name in ("accept_proposal", "reject_proposal", "fork_proposal", "open_pr_proposal"):
        assert not hasattr(backflow_api, name), f"{name} should be removed"
    paths = {getattr(route, "path", "") for route in backflow_api.router.routes}
    for suffix in ("/accept", "/reject", "/fork", "/open-pr"):
        assert not any(path.endswith(suffix) for path in paths), f"{suffix} route should be gone"


def test_sync_backflow_endpoint_triggers_sweep(monkeypatch) -> None:
    """The manual 'sync backflow' still triggers a sweep — pushing backup branches only."""
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    ran = MagicMock(return_value={"backed_up": 1})
    monkeypatch.setattr(backflow_pr_sweep, "run_now", ran)

    result = backflow_api.sync_backflow("Session t")

    ran.assert_called_once()
    assert result["backed_up"] == 1


def test_list_proposals_excludes_bundle_and_adds_agent_name(monkeypatch) -> None:
    monkeypatch.setattr(backflow_api, "_require_admin", lambda _a: SimpleNamespace(name="admin"))
    monkeypatch.setattr(
        backflow_store,
        "list_proposals",
        lambda status="pending": [
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
    )
    monkeypatch.setattr(
        backflow_api.agent_store, "get_by_id", lambda _i: SimpleNamespace(name="support")
    )

    items = backflow_api.list_backflow_proposals(authorization="Session t")

    assert len(items) == 1
    assert "proposed_bundle" not in items[0]  # heavy field excluded from the list
    assert items[0]["agent_name"] == "support"


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
