#!/usr/bin/env python3
"""One-time: push the current local skill pool to an empty external git repo, then enable sync.

Usage:
    python scripts/bootstrap_skill_git.py <remote_url> [branch] [--username U] [--password P]

Refuses if the remote already has the target branch (won't clobber an authoritative repo). On
success records the external source config (enabled=1) so the inbound sweep takes over. Run
once when first adopting GitOps for skills.

NOTE: dulwich ``porcelain.push`` passes auth via kwargs; verify it works against your real
remote before relying on it. If your transport needs different auth, push manually (``git push``)
to an empty remote, then enable sync via the admin API instead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

from fleetent.platform.skill_management import git_source_store, pool_git
from fleetent.skills import registry as skill_registry


def _remote_has_branch(
    pool_dir: Path, remote_url: str, branch: str, username: str | None, password: str | None
) -> bool:
    try:
        pool_git.fetch_remote(
            pool_dir, remote_url=remote_url, branch=branch, username=username, password=password
        )
        return True
    except ValueError:
        return False


def _local_branch_ref(pool_dir: Path) -> str:
    repo = Repo(str(pool_dir))
    try:
        head = repo.refs.read_ref(b"HEAD")
        if head and head.startswith(b"ref: "):
            return head[len(b"ref: ") :].decode()
        return "refs/heads/master"
    finally:
        repo.close()


def bootstrap(
    remote_url: str,
    branch: str = "main",
    *,
    username: str | None = None,
    password: str | None = None,
) -> int:
    """Push the current pool to an empty remote branch and enable inbound sync."""
    pool_dir = Path(skill_registry._resolve_skills_dir(None))
    pool_git.init_pool(pool_dir)
    if _remote_has_branch(pool_dir, remote_url, branch, username, password):
        print(
            f"refusing: remote {remote_url} already has branch {branch!r} "
            "(won't clobber the authoritative repo)",
            file=sys.stderr,
        )
        return 1
    local_ref = _local_branch_ref(pool_dir)
    porcelain.push(
        str(pool_dir),
        remote_url,
        f"{local_ref}:refs/heads/{branch}",
        username=username,
        password=password,
    )
    git_source_store.set_config(enabled=1, remote_url=remote_url, branch=branch)
    print(f"pushed pool to {remote_url} ({branch}); inbound sync enabled")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap external git as the skill source.")
    parser.add_argument("remote_url")
    parser.add_argument("branch", nargs="?", default="main")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args(argv)
    return bootstrap(args.remote_url, args.branch, username=args.username, password=args.password)


if __name__ == "__main__":
    raise SystemExit(main())
