"""Git platform backend factory (skill-git-platform).

Resolves which backend to instantiate from ``config.provider``. An unknown provider logs
a warning and RAISES (unlike the sandbox factory which falls back to docker): pushing to
the wrong authority git repo is dangerous, so we refuse rather than guess. Concrete
backends are imported lazily inside their branch so a Bitbucket-only deployment never
loads the Gitea / GitLab packages.
"""

from __future__ import annotations

from fleetent.integrations.git_platform.backend import BaseGitPlatformBackend
from fleetent.integrations.git_platform.config import GitPlatformConfig
from fleetent.structured_logging import get_logger

_logger = get_logger("git_platform.factory")


def create_git_platform(*, config: GitPlatformConfig) -> BaseGitPlatformBackend:
    """Return the git platform backend for ``config.provider``.

    Raises:
        ValueError: if ``config.provider`` is not a known provider.
    """
    provider = config.provider
    if provider == "bitbucket":
        from fleetent.integrations.git_platform.backends.bitbucket import BitbucketBackend

        return BitbucketBackend(config=config)
    if provider == "gitea":
        from fleetent.integrations.git_platform.backends.gitea import GiteaBackend

        return GiteaBackend(config=config)
    if provider == "gitlab":
        from fleetent.integrations.git_platform.backends.gitlab import GitLabBackend

        return GitLabBackend(config=config)
    _logger.warn("git_platform_unknown_provider", provider=provider)
    raise ValueError(f"unknown git platform provider: {provider!r}")
