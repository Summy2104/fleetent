"""Integration tests for per-skill versioning and current_version backfill.

Covers tasks 2.1–2.2 of skill-pool-git-versioning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.platform.skill_management import pool_git, skill_admin_store
from tests.integration._migration_template import apply_migrations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def pool_dir(tmp_path):
    d = tmp_path / "pool"
    d.mkdir()
    return d


def _make_skill(pool_dir: Path, name: str, content: str = "hello") -> None:
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2.1: per-skill version = subtree last commit; editing A does not change B
# ---------------------------------------------------------------------------


def test_pool_version_for_skill_returns_last_touching_commit(pool_dir):
    pool_git.init_pool(pool_dir)
    _make_skill(pool_dir, "alpha", "v1")
    sha_alpha = pool_git.commit_pool(
        pool_dir, message="edit: alpha", author="admin <a@a.com>", skill_name="alpha"
    )
    _make_skill(pool_dir, "beta", "v1")
    sha_beta = pool_git.commit_pool(
        pool_dir, message="edit: beta", author="admin <a@a.com>", skill_name="beta"
    )

    assert pool_git.pool_version_for_skill(pool_dir, "alpha") == sha_alpha
    assert pool_git.pool_version_for_skill(pool_dir, "beta") == sha_beta


def test_editing_a_does_not_change_b_version(pool_dir):
    pool_git.init_pool(pool_dir)
    _make_skill(pool_dir, "alpha", "v1")
    _make_skill(pool_dir, "beta", "v1")
    # Commit both in one go (init-style), then edit only alpha
    pool_git.commit_pool(pool_dir, message="seed: both", author="system <system@f>")

    beta_version_before = pool_git.pool_version_for_skill(pool_dir, "beta")

    # Edit only alpha
    _make_skill(pool_dir, "alpha", "v2")
    pool_git.commit_pool(
        pool_dir, message="edit: alpha v2", author="admin <a@a.com>", skill_name="alpha"
    )

    beta_version_after = pool_git.pool_version_for_skill(pool_dir, "beta")

    # beta's version must not change
    assert beta_version_before is not None
    assert beta_version_before == beta_version_after

    # alpha's version must advance
    alpha_version = pool_git.pool_version_for_skill(pool_dir, "alpha")
    assert alpha_version != beta_version_after


def test_pool_version_for_nonexistent_skill_returns_none(pool_dir):
    pool_git.init_pool(pool_dir)
    assert pool_git.pool_version_for_skill(pool_dir, "nonexistent") is None


# ---------------------------------------------------------------------------
# 2.2: current_version updated after edit; backfill on upgrade init
# ---------------------------------------------------------------------------


def test_current_version_updated_after_pool_edit(db, pool_dir):
    """After committing a skill edit, current_version reflects the new sha."""
    pool_git.init_pool(pool_dir)
    _make_skill(pool_dir, "crm-ops", "v1")
    sha = pool_git.commit_pool(
        pool_dir, message="edit: crm-ops", author="admin <a@a.com>", skill_name="crm-ops"
    )
    assert sha is not None

    # Caller is responsible for updating current_version after commit
    skill_admin_store.set_current_version("crm-ops", sha)

    row = skill_admin_store.get_source("crm-ops")
    assert row["current_version"] == sha


def test_backfill_current_versions_sets_all_skills(db, pool_dir):
    """backfill_current_versions populates current_version for every pool skill."""
    pool_git.init_pool(pool_dir)
    _make_skill(pool_dir, "skill-a", "v1")
    _make_skill(pool_dir, "skill-b", "v1")
    pool_git.commit_pool(pool_dir, message="seed", author="system <system@f>")

    # Ensure catalog rows exist before backfill
    skill_admin_store.ensure_catalog_entries(["skill-a", "skill-b"])

    # backfill
    pool_git.backfill_current_versions(pool_dir, skill_admin_store.set_current_version)

    row_a = skill_admin_store.get_source("skill-a")
    row_b = skill_admin_store.get_source("skill-b")
    assert row_a["current_version"] is not None
    assert row_b["current_version"] is not None
    # Both committed in the same commit so their versions should be equal
    assert row_a["current_version"] == row_b["current_version"]


def test_backfill_does_not_overwrite_newer_version(db, pool_dir):
    """Backfill reads pool_version_for_skill, so it reflects the latest commit."""
    pool_git.init_pool(pool_dir)
    _make_skill(pool_dir, "skill-x", "v1")
    sha1 = pool_git.commit_pool(pool_dir, message="seed", author="system <system@f>")

    _make_skill(pool_dir, "skill-x", "v2")
    sha2 = pool_git.commit_pool(
        pool_dir, message="edit: skill-x v2", author="admin <a@a.com>", skill_name="skill-x"
    )
    assert sha2 is not None
    assert sha1 != sha2

    skill_admin_store.ensure_catalog_entries(["skill-x"])
    pool_git.backfill_current_versions(pool_dir, skill_admin_store.set_current_version)

    row = skill_admin_store.get_source("skill-x")
    assert row["current_version"] == sha2
