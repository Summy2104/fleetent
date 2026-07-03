"""Unit tests for the outbound backflow PR sweep (skill-backflow-git-pr).

The sweep pushes ONE aggregate backup branch per agent (all its drifted skills), degrading
to ``deferred`` (never raising) when git is unreachable, and never opening PRs. A
FakeGitPlatformBackend is injected; git_source_store / backflow_store are patched. Also
guards that the nominate / node-ingestion path stays git-free.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fleetent import agent_store
from fleetent.integrations.git_platform import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
    GitPlatformUnavailableError,
    PullRequestRef,
)
from fleetent.platform.skill_management import backflow_pr_sweep, backflow_store, git_source_store


def _stub_agent(monkeypatch, agent_id: int, name: str) -> None:
    monkeypatch.setattr(
        agent_store,
        "get_by_id",
        lambda aid: SimpleNamespace(name=name) if aid == agent_id else None,
    )


@pytest.fixture(autouse=True)
def _sweep_defaults(monkeypatch):
    """Defaults for the backup/PR-focused tests: no drift to nominate, and nothing already
    landed (so an empty temp pool dir doesn't accidentally mark proposals merged)."""
    monkeypatch.setattr(backflow_pr_sweep.skill_admin_store, "list_drifted", lambda: [])
    monkeypatch.setattr(backflow_store, "is_landed", lambda *_a, **_k: False)


_CONFIG = {
    "enabled": 1,
    "provider": "fake",
    "remote_url": "https://git/scm/p/skills.git",
    "branch": "main",
    "branch_prefix": "backflow",
    "auto_open_pr": 0,
}


class _FakeBackend(BaseGitPlatformBackend):
    name = "fake"
    capabilities = GitPlatformCapabilities(
        open_pr=True, merge_pr=True, close_pr=True, query_pr=True
    )

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.pushed: list[dict] = []
        self.opened: list[dict] = []

    def available(self) -> bool:
        return not self.unavailable

    def push_branch(self, *, branch, bundle, subdir, base_ref, message, author) -> str:
        if self.unavailable:
            raise GitPlatformUnavailableError("remote down")
        self.pushed.append(
            {"branch": branch, "subdir": subdir, "base_ref": base_ref, "bundle": bundle}
        )
        return f"sha-{branch}"

    def open_pull_request(
        self, *, source_branch, target_branch, title, description=""
    ) -> PullRequestRef:
        if self.unavailable:
            raise GitPlatformUnavailableError("remote down")
        self.opened.append({"source": source_branch, "target": target_branch})
        return PullRequestRef(
            pr_id="99", url="https://pr/99", state="open", source_branch=source_branch
        )


def _patch_states(monkeypatch, *, unbacked=(), deferred=(), backed_up=()) -> None:
    proposals = {None: list(unbacked), "deferred": list(deferred), "backed_up": list(backed_up)}
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: proposals[state])


def test_backs_up_agent_aggregate_branch(monkeypatch) -> None:
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        unbacked=[
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    set_link = MagicMock()
    set_state = MagicMock()
    monkeypatch.setattr(backflow_store, "set_pr_link", set_link)
    monkeypatch.setattr(backflow_store, "set_pr_state", set_state)

    backflow_pr_sweep.sweep()

    # One aggregate branch per agent (no skill in the name); bundle keys are "<skill>/<relpath>".
    assert fake.pushed == [
        {
            "branch": "backflow/Sales-Bot",
            "subdir": "",
            "base_ref": "main",
            "bundle": {"crm-ops/SKILL.md": "x"},
        }
    ]
    set_link.assert_any_call(1, branch="backflow/Sales-Bot")
    set_state.assert_any_call(1, "backed_up")


def test_aggregates_multiple_skills_from_one_agent_into_one_branch(monkeypatch) -> None:
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        unbacked=[
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "a"}},
            {"id": 2, "agent_id": 7, "skill_name": "billing", "proposed_bundle": {"SKILL.md": "b"}},
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    set_state = MagicMock()
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", set_state)

    backflow_pr_sweep.sweep()

    # Both skills land on the SAME branch, each under its own "<skill>/..." path.
    assert len(fake.pushed) == 1
    push = fake.pushed[0]
    assert push["branch"] == "backflow/Sales-Bot"
    assert push["bundle"] == {"crm-ops/SKILL.md": "a", "billing/SKILL.md": "b"}
    set_state.assert_any_call(1, "backed_up")
    set_state.assert_any_call(2, "backed_up")


def test_backs_up_with_skills_subdir_prefixes_tree_path(monkeypatch) -> None:
    fake = _FakeBackend()
    config = {**_CONFIG, "skills_subdir": "skills"}
    monkeypatch.setattr(git_source_store, "get_config", lambda: config)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        unbacked=[
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())

    backflow_pr_sweep.sweep()

    assert fake.pushed == [
        {
            "branch": "backflow/Sales-Bot",
            "subdir": "skills",
            "base_ref": "main",
            "bundle": {"crm-ops/SKILL.md": "x"},
        }
    ]


def test_branch_name_falls_back_to_agent_id_when_agent_missing(monkeypatch) -> None:
    monkeypatch.setattr(agent_store, "get_by_id", lambda _aid: None)
    assert backflow_pr_sweep._branch_name({"branch_prefix": "backflow"}, 7) == "backflow/7"


def test_branch_name_sanitizes_unsafe_agent_name(monkeypatch) -> None:
    _stub_agent(monkeypatch, 7, "Ops/Team #1 ~weird")
    # Illegal ref characters collapse to '-'; no '/', '~', '#', or spaces leak through.
    assert (
        backflow_pr_sweep._branch_name({"branch_prefix": "backflow"}, 7)
        == "backflow/Ops-Team-1-weird"
    )


def test_skips_repush_when_agent_set_unchanged(monkeypatch) -> None:
    """An agent whose skills are all already backed_up (and none landed) is not re-pushed —
    a fresh identical snapshot would only churn the open PR."""
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        backed_up=[
            {
                "id": 2,
                "agent_id": 7,
                "skill_name": "crm-ops",
                "proposed_bundle": {"SKILL.md": "x"},
                "pr_state": "backed_up",
            }
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())

    backflow_pr_sweep.sweep()

    assert fake.pushed == []  # nothing changed -> no re-push


def test_landed_proposal_marked_merged_and_dropped(monkeypatch) -> None:
    """A proposal whose evolved copy already equals the pool (merged + synced back) is marked
    ``merged`` and not pushed."""
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "is_landed", lambda *_a, **_k: True)
    _patch_states(
        monkeypatch,
        backed_up=[
            {
                "id": 2,
                "agent_id": 7,
                "skill_name": "crm-ops",
                "proposed_bundle": {"SKILL.md": "x"},
                "pr_state": "backed_up",
            }
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    set_state = MagicMock()
    monkeypatch.setattr(backflow_store, "set_pr_state", set_state)

    backflow_pr_sweep.sweep()

    set_state.assert_any_call(2, "merged")
    assert fake.pushed == []


def test_sweep_never_opens_pr_even_with_auto_open(monkeypatch) -> None:
    """The platform only pushes backup branches; opening a PR to the authority branch is the
    human's job. The sweep must never open a PR, even if a legacy auto_open_pr=1 lingers."""
    fake = _FakeBackend()
    config = {**_CONFIG, "auto_open_pr": 1}
    monkeypatch.setattr(git_source_store, "get_config", lambda: config)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        unbacked=[
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())

    result = backflow_pr_sweep.sweep()

    assert fake.opened == []  # never opens a PR
    assert "prs_opened" not in result or result["prs_opened"] == 0


def test_git_unreachable_defers_without_raising(monkeypatch) -> None:
    fake = _FakeBackend(unavailable=True)
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    _patch_states(
        monkeypatch,
        unbacked=[
            {"id": 3, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
    )
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    defer_state = MagicMock()
    monkeypatch.setattr(backflow_store, "defer_pr_state", defer_state)

    backflow_pr_sweep.sweep()  # must not raise

    defer_state.assert_any_call(3)


def test_disabled_source_is_a_noop(monkeypatch) -> None:
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: {"enabled": 0})
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)

    result = backflow_pr_sweep.sweep()

    assert fake.pushed == []
    assert result.get("backed_up") == 0


def test_sweep_nominates_drifted_skills_off_the_request_path(monkeypatch) -> None:
    """The sweep (not status ingestion) nominates drifted skills, bounded per round."""
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: [])
    monkeypatch.setattr(
        backflow_pr_sweep.skill_admin_store,
        "list_drifted",
        lambda: [(7, "crm-ops"), (8, "billing")],
    )
    calls: list[tuple[int, str]] = []

    def _nominate(*, agent_id, skill_name, pool_dir):
        calls.append((agent_id, skill_name))
        return 100 + agent_id  # truthy proposal id

    monkeypatch.setattr(backflow_store, "nominate_if_absent", _nominate)

    result = backflow_pr_sweep.sweep()

    assert calls == [(7, "crm-ops"), (8, "billing")]
    assert result["nominated"] == 2


def test_sweep_nominate_budget_caps_per_round(monkeypatch) -> None:
    """One round nominates at most _NOMINATE_BUDGET_PER_ROUND skills (rest picked up next)."""
    monkeypatch.setattr(git_source_store, "get_config", lambda: {"enabled": 0})
    over = [(i, f"skill-{i}") for i in range(backflow_pr_sweep._NOMINATE_BUDGET_PER_ROUND + 10)]
    monkeypatch.setattr(backflow_pr_sweep.skill_admin_store, "list_drifted", lambda: over)
    monkeypatch.setattr(backflow_store, "nominate_if_absent", lambda **_: 1)

    result = backflow_pr_sweep.sweep()

    assert result["nominated"] == backflow_pr_sweep._NOMINATE_BUDGET_PER_ROUND


def test_nominate_and_node_ingestion_path_are_git_free() -> None:
    # The nominate path and the node desired-state API must not touch external git:
    # git operations live only in the sweep / governance, never on the ingestion path.
    from fleetent.platform.node_management import node_desired_state_api

    store_src = Path(backflow_store.__file__).read_text()
    node_src = Path(node_desired_state_api.__file__).read_text()
    for token in ("git_platform", "push_branch", "open_pull_request"):
        assert token not in store_src, f"{token} leaked into backflow_store (nominate path)"
        assert token not in node_src, f"{token} leaked into node_desired_state_api"
