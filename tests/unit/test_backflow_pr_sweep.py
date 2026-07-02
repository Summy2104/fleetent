"""Unit tests for the outbound backflow PR sweep (skill-backflow-git-pr).

The sweep pushes a backup branch for unbacked proposals, then opens a PR for backed-up
ones when auto_open_pr is set, degrading to ``deferred`` (never raising) when git is
unreachable. A FakeGitPlatformBackend is injected; git_source_store / backflow_store are
patched. Also guards that the nominate / node-ingestion path stays git-free.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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
        self.pushed.append({"branch": branch, "subdir": subdir, "base_ref": base_ref})
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


def test_backs_up_unbacked_proposal_on_a_non_main_branch(monkeypatch) -> None:
    fake = _FakeBackend()
    proposals = {
        None: [
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
        "deferred": [],
        "backed_up": [],
    }
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: proposals[state])
    # Branch names use the agent's (human) name, sanitized to a legal ref component.
    _stub_agent(monkeypatch, 7, "Sales Bot")
    set_link = MagicMock()
    set_state = MagicMock()
    monkeypatch.setattr(backflow_store, "set_pr_link", set_link)
    monkeypatch.setattr(backflow_store, "set_pr_state", set_state)

    backflow_pr_sweep.sweep()

    assert fake.pushed == [
        {"branch": "backflow/Sales-Bot/crm-ops", "subdir": "crm-ops", "base_ref": "main"}
    ]
    set_link.assert_any_call(1, branch="backflow/Sales-Bot/crm-ops")
    set_state.assert_any_call(1, "backed_up")


def test_backs_up_with_skills_subdir_prefixes_tree_path(monkeypatch) -> None:
    fake = _FakeBackend()
    config = {**_CONFIG, "skills_subdir": "skills"}
    proposals = {
        None: [
            {"id": 1, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
        "deferred": [],
        "backed_up": [],
    }
    monkeypatch.setattr(git_source_store, "get_config", lambda: config)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: proposals[state])
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())

    backflow_pr_sweep.sweep()

    assert fake.pushed == [
        {"branch": "backflow/Sales-Bot/crm-ops", "subdir": "skills/crm-ops", "base_ref": "main"}
    ]


def test_branch_name_falls_back_to_agent_id_when_agent_missing(monkeypatch) -> None:
    monkeypatch.setattr(agent_store, "get_by_id", lambda _aid: None)
    branch = backflow_pr_sweep._branch_name(
        {"branch_prefix": "backflow"}, {"agent_id": 7, "skill_name": "crm-ops"}
    )
    assert branch == "backflow/7/crm-ops"


def test_branch_name_sanitizes_unsafe_agent_name(monkeypatch) -> None:
    _stub_agent(monkeypatch, 7, "Ops/Team #1 ~weird")
    branch = backflow_pr_sweep._branch_name(
        {"branch_prefix": "backflow"}, {"agent_id": 7, "skill_name": "crm-ops"}
    )
    # Illegal ref characters collapse to '-'; no '/', '~', '#', or spaces leak through.
    assert branch == "backflow/Ops-Team-1-weird/crm-ops"


def test_sweep_never_opens_pr_even_with_auto_open(monkeypatch) -> None:
    """The platform only pushes backup branches; opening a PR to the authority branch is
    the human's job. The sweep must never open a PR, even if a legacy auto_open_pr=1 config
    lingers."""
    fake = _FakeBackend()
    config = {**_CONFIG, "auto_open_pr": 1}
    proposals = {
        None: [],
        "deferred": [],
        "backed_up": [
            {"id": 2, "agent_id": 7, "skill_name": "crm-ops", "pr_branch": "backflow/7/crm-ops"}
        ],
    }
    monkeypatch.setattr(git_source_store, "get_config", lambda: config)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: proposals[state])
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    monkeypatch.setattr(backflow_store, "set_pr_state", MagicMock())

    result = backflow_pr_sweep.sweep()

    assert fake.opened == []  # never opens a PR
    assert "prs_opened" not in result or result["prs_opened"] == 0


def test_git_unreachable_defers_without_raising(monkeypatch) -> None:
    fake = _FakeBackend(unavailable=True)
    proposals = {
        None: [
            {"id": 3, "agent_id": 7, "skill_name": "crm-ops", "proposed_bundle": {"SKILL.md": "x"}}
        ],
        "deferred": [],
        "backed_up": [],
    }
    monkeypatch.setattr(git_source_store, "get_config", lambda: _CONFIG)
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)
    monkeypatch.setattr(backflow_store, "list_by_pr_state", lambda state, **_: proposals[state])
    _stub_agent(monkeypatch, 7, "Sales Bot")
    monkeypatch.setattr(backflow_store, "set_pr_link", MagicMock())
    defer_state = MagicMock()
    monkeypatch.setattr(backflow_store, "defer_pr_state", defer_state)

    # Must not raise.
    backflow_pr_sweep.sweep()

    defer_state.assert_any_call(3)


def test_disabled_source_is_a_noop(monkeypatch) -> None:
    fake = _FakeBackend()
    monkeypatch.setattr(git_source_store, "get_config", lambda: {"enabled": 0})
    monkeypatch.setattr(backflow_pr_sweep, "_backend_factory", lambda _c: fake)

    result = backflow_pr_sweep.sweep()

    assert fake.pushed == []
    assert result.get("backed_up") == 0


def test_nominate_and_node_ingestion_path_are_git_free() -> None:
    # The nominate path and the node desired-state API must not touch external git:
    # git operations live only in the sweep / governance, never on the ingestion path.
    from fleetent.platform.node_management import node_desired_state_api

    store_src = Path(backflow_store.__file__).read_text()
    node_src = Path(node_desired_state_api.__file__).read_text()
    for token in ("git_platform", "push_branch", "open_pull_request"):
        assert token not in store_src, f"{token} leaked into backflow_store (nominate path)"
        assert token not in node_src, f"{token} leaked into node_desired_state_api"
