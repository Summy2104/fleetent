"""Pluggable git platform integration (skill-git-platform).

Public surface for pushing backup / fork branches and driving the pull-request lifecycle
on a self-hostable git platform (Bitbucket first; Gitea / GitLab stubbed). Used only by
``platform.skill_management`` backflow; this package never depends on ``platform.*``.
"""

from __future__ import annotations

from fleetent.integrations.git_platform.backend import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
    GitPlatformUnavailableError,
    PullRequestRef,
)
from fleetent.integrations.git_platform.config import GitPlatformConfig
from fleetent.integrations.git_platform.factory import create_git_platform

__all__ = [
    "BaseGitPlatformBackend",
    "GitPlatformCapabilities",
    "GitPlatformConfig",
    "GitPlatformUnavailableError",
    "PullRequestRef",
    "create_git_platform",
]
