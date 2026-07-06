"""Pluggable git platform backend abstraction (skill-git-platform).

The backend abstraction is the single seam every git hosting platform implements:
Bitbucket today, Gitea / GitLab stubbed alongside it. The mandatory surface is
``available`` (a probe that never raises) and ``push_branch`` (the only operation that
speaks the raw git protocol, via dulwich -- used to push backup / fork branches). The
capability-gated surface (``open_pull_request`` / ``get_pull_request`` /
``merge_pull_request`` / ``close_pull_request``) goes through the platform's REST API and
is only meaningful on backends that declare the matching ``GitPlatformCapabilities`` flag
-- callers gate on the capability rather than the concrete type (no isinstance).

All git interaction lives platform-side; node and agent never touch external git.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


class GitPlatformUnavailableError(RuntimeError):
    """Raised when a remote git platform is unreachable or a push/PR op cannot complete.

    Surfaced instead of letting a raw transport / HTTP error escape, so callers can
    degrade deterministically (mark the proposal ``deferred`` and retry) rather than
    crashing the sweep or mutating governance state on a transient failure.
    """


@dataclass(frozen=True)
class GitPlatformCapabilities:
    """What a backend can do beyond the mandatory ``available`` / ``push_branch`` core.

    Callers gate the PR lifecycle on these flags so a backend that cannot open / merge /
    close / query a pull request degrades gracefully instead of erroring. Frozen so a
    backend's declared capabilities are an immutable contract.
    """

    open_pr: bool
    merge_pr: bool
    close_pr: bool
    query_pr: bool
    server_side_merge: bool = False
    delete_source_branch: bool = False


@dataclass(frozen=True)
class PullRequestRef:
    """A reference to a pull request on the git platform.

    ``state`` is normalised to ``open`` / ``merged`` / ``closed`` across providers.
    ``merge_commit`` is populated only once the PR is merged.
    """

    pr_id: str
    url: str
    state: str
    source_branch: str
    merge_commit: str | None = None


class BaseGitPlatformBackend(ABC):
    """Abstract base every git platform backend extends.

    Subclasses set the ``name`` / ``capabilities`` class attributes and implement the
    mandatory core (``available`` / ``push_branch``); the PR lifecycle methods are
    capability-gated and raise ``NotImplementedError`` here so a caller that ignores the
    capability flag fails loudly rather than silently no-opping.
    """

    name: ClassVar[str]
    capabilities: ClassVar[GitPlatformCapabilities]

    @abstractmethod
    def available(self) -> bool:
        """Probe whether the platform is reachable. MUST NOT raise (return False)."""

    @abstractmethod
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
        """Push ``bundle`` (relpath -> content) under ``subdir`` as a new ``branch``.

        Branches off ``base_ref`` (typically the authority branch). Returns the new
        branch's commit id. Raises ``GitPlatformUnavailable`` if the remote is
        unreachable.
        """

    def open_pull_request(
        self, *, source_branch: str, target_branch: str, title: str, description: str = ""
    ) -> PullRequestRef:
        raise NotImplementedError(f"{type(self).__name__} does not support opening pull requests")

    def get_pull_request(self, pr_id: str) -> PullRequestRef:
        raise NotImplementedError(f"{type(self).__name__} does not support querying pull requests")

    def merge_pull_request(self, pr_id: str) -> PullRequestRef:
        raise NotImplementedError(f"{type(self).__name__} does not support merging pull requests")

    def close_pull_request(self, pr_id: str) -> PullRequestRef:
        raise NotImplementedError(f"{type(self).__name__} does not support closing pull requests")
