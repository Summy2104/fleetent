"""Deployment status and redeploy orchestration helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentStatus:
    deployed_commit: str
    head_commit: str
    is_stale: bool
    message: str


def compare_commits(*, deployed_commit: str, head_commit: str) -> DeploymentStatus:
    """Compare a running deployment commit with the source checkout HEAD."""
    deployed = deployed_commit.strip() or "unknown"
    head = head_commit.strip() or "unknown"
    if deployed == head:
        return DeploymentStatus(
            deployed_commit=deployed,
            head_commit=head,
            is_stale=False,
            message=f"deployment current: {head}",
        )
    return DeploymentStatus(
        deployed_commit=deployed,
        head_commit=head,
        is_stale=True,
        message=f"deployment stale: deployed={deployed} head={head}",
    )


def redeploy(*, build: Callable[[], int], restart: Callable[[], int]) -> int:
    """Run build before restart; leave running services untouched if build fails."""
    build_code = build()
    if build_code != 0:
        return build_code
    return restart()
