"""Integration test: pool_git remote-sync primitives.

Two real dulwich repos (source + pool), no network. Verifies:
  - fetch_remote returns the remote branch's commit sha
  - reset_pool_to hard-mirrors the working tree AND advances the pool's per-skill version
  - list_pool_skills enumerates skill dirs (excludes .git)
  - an unknown branch raises ValueError
  - incremental fetch picks up new commits
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

from fleetent.platform.skill_management import pool_git


def _write_skill(repo_dir: Path, name: str, body: str) -> None:
    sd = repo_dir / name
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} desc\n---\n# {body}\n", encoding="utf-8"
    )


def _commit_all(repo_dir: Path, message: bytes) -> str:
    porcelain.add(str(repo_dir))
    sha = porcelain.commit(str(repo_dir), message=message, author=b"t <t@t>", committer=b"t <t@t>")
    return sha.decode() if isinstance(sha, bytes) else sha


def _make_source(tmp_path: Path) -> tuple[Path, str, str]:
    source = tmp_path / "source"
    source.mkdir()
    porcelain.init(str(source))
    _write_skill(source, "demo-skill", "Demo")
    sha = _commit_all(source, b"add demo-skill")
    repo = Repo(str(source))
    try:
        head = repo.refs.read_ref(b"HEAD")
        branch = head.decode().split("refs/heads/")[-1] if head else "master"
    finally:
        repo.close()
    return source, sha, branch


def _init_pool(tmp_path: Path, source: Path) -> Path:
    pool = tmp_path / "pool"
    pool.mkdir()
    pool_git.init_pool_with_remote(pool, remote_url=str(source))
    return pool


def test_fetch_and_reset_mirrors_source(tmp_path) -> None:
    source, src_sha, branch = _make_source(tmp_path)
    pool = _init_pool(tmp_path, source)

    remote_sha = pool_git.fetch_remote(
        pool, remote_url=str(source), branch=branch, username=None, password=None
    )
    assert remote_sha == src_sha

    pool_git.reset_pool_to(pool, remote_sha)
    skill_md = pool / "demo-skill" / "SKILL.md"
    assert skill_md.exists()
    assert "Demo" in skill_md.read_text(encoding="utf-8")
    assert "demo-skill" in pool_git.list_pool_skills(pool)
    assert pool_git.pool_version_for_skill(pool, "demo-skill") == remote_sha


def test_fetch_branch_not_found_raises(tmp_path) -> None:
    source, _sha, _branch = _make_source(tmp_path)
    pool = _init_pool(tmp_path, source)
    with pytest.raises(ValueError):
        pool_git.fetch_remote(
            pool, remote_url=str(source), branch="nonexistent", username=None, password=None
        )


def test_fetch_incremental_picks_up_new_commit(tmp_path) -> None:
    source, first_sha, branch = _make_source(tmp_path)
    pool = _init_pool(tmp_path, source)
    pool_git.reset_pool_to(
        pool,
        pool_git.fetch_remote(
            pool, remote_url=str(source), branch=branch, username=None, password=None
        ),
    )

    _write_skill(source, "second-skill", "Second")
    second_sha = _commit_all(source, b"add second-skill")
    assert second_sha != first_sha

    remote_sha = pool_git.fetch_remote(
        pool, remote_url=str(source), branch=branch, username=None, password=None
    )
    assert remote_sha == second_sha
    pool_git.reset_pool_to(pool, remote_sha)
    assert set(pool_git.list_pool_skills(pool)) >= {"demo-skill", "second-skill"}
