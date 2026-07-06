"""Git platform backend config (skill-git-platform).

A plain, platform-agnostic value object the caller builds from the ``skill_git_source``
row plus credential values resolved out of ``agent_secrets`` (the package never reads the
DB or secret store itself -- it must not depend on ``platform.*``). Credentials are passed
already-resolved so the package stays a pure git/REST adapter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitPlatformConfig:
    """Resolved configuration for a git platform backend.

    ``remote_url`` / ``branch`` / ``branch_prefix`` / ``auto_open_pr`` come from the
    ``skill_git_source`` row; ``base_url`` / ``project`` / ``repo`` locate the REST API;
    ``username`` / ``token`` are the already-decrypted credentials (env-name indirection
    is resolved by the caller).
    """

    provider: str
    remote_url: str
    branch: str
    branch_prefix: str
    auto_open_pr: bool
    base_url: str | None = None
    project: str | None = None
    repo: str | None = None
    username: str | None = None
    token: str | None = None
