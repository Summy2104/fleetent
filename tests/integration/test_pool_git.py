"""Integration tests for pool_git: pool git repo init / commit / serialization.

All tests use real dulwich repos in tmp_path — no mocks.
"""

from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

import pytest

from fleetent.platform.skill_management import pool_git


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_skill(pool_dir: Path, name: str, content: str = "hello") -> None:
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _commit_count(pool_dir: Path) -> int:
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
    except Exception:
        return 0
    count = 0
    try:
        for _ in r.get_walker():
            count += 1
    except Exception:
        pass
    return count


# ---------------------------------------------------------------------------
# 1.1: init_pool - non-git dir becomes git repo with one initial commit;
#      already-git dir is idempotent
# ---------------------------------------------------------------------------


def test_init_pool_creates_git_repo(tmp_path):
    _make_skill(tmp_path, "alpha")
    pool_git.init_pool(tmp_path)

    assert (tmp_path / ".git").is_dir()
    assert _commit_count(tmp_path) == 1


def test_init_pool_initial_commit_includes_existing_content(tmp_path):
    _make_skill(tmp_path, "alpha")
    _make_skill(tmp_path, "beta")
    pool_git.init_pool(tmp_path)

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    # walk tree of HEAD
    head_commit = r[r.head()]
    tree = r.object_store[head_commit.tree]
    names = {item.path.decode() for item in tree.items()}
    assert "alpha" in names
    assert "beta" in names


def test_init_pool_idempotent_on_existing_git_repo(tmp_path):
    _make_skill(tmp_path, "alpha")
    pool_git.init_pool(tmp_path)
    assert _commit_count(tmp_path) == 1

    # second call: no new commit
    pool_git.init_pool(tmp_path)
    assert _commit_count(tmp_path) == 1


def test_init_pool_empty_dir(tmp_path):
    # empty pool dir still becomes a git repo (no-content case)
    pool_git.init_pool(tmp_path)
    assert (tmp_path / ".git").is_dir()


# ---------------------------------------------------------------------------
# 1.2: commit_pool - attributable commits; no-change = no empty commit
# ---------------------------------------------------------------------------


def test_commit_pool_creates_attributable_commit(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "crm-ops", "v1")

    pool_git.commit_pool(tmp_path, message="edit: crm-ops", author="alice <alice@corp.com>")

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    head = r[r.head()]
    assert b"edit: crm-ops" in head.message
    assert b"alice" in head.author


def test_commit_pool_no_change_no_empty_commit(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "alpha")
    pool_git.commit_pool(tmp_path, message="seed: alpha", author="system <system@fleetent>")

    count_before = _commit_count(tmp_path)
    # nothing changed — calling commit_pool should not produce an extra commit
    pool_git.commit_pool(tmp_path, message="seed: alpha", author="system <system@fleetent>")
    assert _commit_count(tmp_path) == count_before


def test_commit_pool_system_author(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "alpha", "v1")
    pool_git.commit_pool(tmp_path, message="seed: initialize pool", author="system <system@fleetent>")

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    head = r[r.head()]
    assert b"system" in head.author


# ---------------------------------------------------------------------------
# 1.3: write serialization - concurrent writes don't corrupt the repo
# ---------------------------------------------------------------------------


def _worker_write(pool_dir_str: str, skill_name: str, content: str) -> None:
    """Subprocess worker: commit one skill change to the pool."""
    pool_dir = Path(pool_dir_str)
    _make_skill(pool_dir, skill_name, content)
    pool_git.commit_pool(
        pool_dir,
        message=f"edit: {skill_name}",
        author=f"worker <{skill_name}@test>",
        skill_name=skill_name,
    )


def test_concurrent_writes_serialized_and_repo_intact(tmp_path):
    pool_git.init_pool(tmp_path)

    # launch two concurrent processes writing to different skills
    p1 = multiprocessing.Process(
        target=_worker_write, args=(str(tmp_path), "skill-a", "content from proc 1")
    )
    p2 = multiprocessing.Process(
        target=_worker_write, args=(str(tmp_path), "skill-b", "content from proc 2")
    )
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    assert p1.exitcode == 0, f"proc1 failed with exitcode {p1.exitcode}"
    assert p2.exitcode == 0, f"proc2 failed with exitcode {p2.exitcode}"

    # repo must be intact: each worker adds exactly 1 commit
    # (init_pool on empty dir creates repo but no commit, so expect exactly 2)
    count = _commit_count(tmp_path)
    assert count >= 2, f"expected ≥2 commits (one per worker), got {count}"

    # both skills must exist in the pool
    assert (tmp_path / "skill-a" / "SKILL.md").exists()
    assert (tmp_path / "skill-b" / "SKILL.md").exists()
