"""Unit tests for the pluggable git platform factory + base contract (skill-git-platform).

Covers provider selection, unknown-provider rejection (raise, never fall back -- writing
to the wrong authority git is dangerous), and capability-gated PR surface on the base.
"""

from __future__ import annotations

import pytest

from fleetent.integrations.git_platform import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
    GitPlatformConfig,
    create_git_platform,
)


def _cfg(provider: str) -> GitPlatformConfig:
    return GitPlatformConfig(
        provider=provider,
        remote_url="https://git.example.com/scm/proj/skills.git",
        branch="main",
        branch_prefix="backflow",
        auto_open_pr=True,
        base_url="https://git.example.com",
        project="proj",
        repo="skills",
        username="bot",
        token="secret-token",
    )


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        create_git_platform(config=_cfg("does-not-exist"))


def test_base_pr_methods_are_capability_gated() -> None:
    # A backend declaring no PR capabilities must raise NotImplementedError on the
    # capability-gated surface; callers gate on the capability flag, never isinstance.
    class _Bare(BaseGitPlatformBackend):
        name = "bare"
        capabilities = GitPlatformCapabilities(
            open_pr=False, merge_pr=False, close_pr=False, query_pr=False
        )

        def available(self) -> bool:
            return True

        def push_branch(
            self,
            *,
            branch: str,
            bundle: dict[str, str],
            subdir: str,
            base_ref: str,
            message: str,
            author: str,
        ) -> str:
            return "sha"

    bare = _Bare()
    assert bare.capabilities.open_pr is False
    with pytest.raises(NotImplementedError):
        bare.open_pull_request(source_branch="b", target_branch="main", title="t")
    with pytest.raises(NotImplementedError):
        bare.merge_pull_request(pr_id="1")
