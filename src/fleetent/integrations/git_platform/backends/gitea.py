"""Gitea / Forgejo git platform backend (skill-git-platform) -- stub.

Declares no capabilities until implemented; the factory selects it but every operation
raises ``NotImplementedError`` so a misconfiguration fails loudly rather than silently.
"""

from __future__ import annotations

from fleetent.integrations.git_platform.backend import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
)
from fleetent.integrations.git_platform.config import GitPlatformConfig


class GiteaBackend(BaseGitPlatformBackend):
    name = "gitea"
    capabilities = GitPlatformCapabilities(
        open_pr=False, merge_pr=False, close_pr=False, query_pr=False
    )

    def __init__(self, *, config: GitPlatformConfig) -> None:
        self.config = config

    def available(self) -> bool:
        return False

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
        raise NotImplementedError("gitea backend is not yet implemented")
