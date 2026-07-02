"""Integration tests for materialize base_version upgrade to git identifier.

Covers tasks 3.1–3.4 of skill-pool-git-versioning:
- materialize writes git sha as base_version (3.1)
- content-hash base_version on upgrade → no false drift + re-baseline (3.2)
- after re-baseline drift detection uses git content comparison (3.3)
- copytree pool→agent home excludes .git (3.4)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent import agent_store
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.skill_management import skill_admin_store
from fleetent.platform.tenancy import store as tenancy_store
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


def _setup_pool_skill(pool_dir: Path, name: str, content: str = "hello") -> str:
    """Create a skill in the pool, commit it, return the commit sha."""
    from fleetent.platform.skill_management import pool_git

    # Init on empty dir first so skill creation goes in its own commit
    pool_git.init_pool(pool_dir)
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    sha = pool_git.commit_pool(
        pool_dir, message=f"seed: {name}", author="system <system@f>", skill_name=name
    )
    assert sha is not None, f"commit_pool returned None for skill {name!r}"
    return sha


def _setup_subdir_pool_skill(git_root: Path, subdir: str, name: str, content: str = "hello") -> str:
    """Init a git repo at ``git_root``, commit a skill under ``<git_root>/<subdir>/<name>``.

    Mirrors ``_setup_pool_skill`` but for the subdir-mirrored production layout where the
    git root (``.git``) and the skill scan root (``<git_root>/<subdir>``) are different
    directories. Returns the commit sha.
    """
    from fleetent.platform.skill_management import pool_git

    pool_git.init_pool(git_root)
    skill_dir = git_root / subdir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    sha = pool_git.commit_pool(
        pool_dir=git_root,
        message=f"seed: {name}",
        author="system <system@f>",
        skill_name=name,
        subdir=subdir,
    )
    assert sha is not None, f"commit_pool returned None for skill {name!r}"
    return sha


def _create_agent(db, name: str = "support") -> agent_store.Agent:
    tenancy_store.create_tenant(id="acme", name="Acme")
    return agent_store.create_agent(name, "You are support.", [], tenant_id="acme")


# ---------------------------------------------------------------------------
# 3.1: materialize writes git sha as base_version
# ---------------------------------------------------------------------------


def test_materialize_writes_content_hash_base_version(db, pool_dir, tmp_path, monkeypatch):
    """After materialize, base_version is a sha256 content hash of the skill dir.

    The pool git sha is tracked separately in current_version (catalog); base_version
    is always a content hash so that drift detection (home modified?) works correctly
    even when the pool is updated between materializations.
    """
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha = _setup_pool_skill(pool_dir, "billing", "billing skill content")
    skill_admin_store.set_current_version("billing", sha)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    drift_row = skill_admin_store.get_drift(agent.id, "billing")
    base_version = drift_row["base_version"]
    base_commit = drift_row["base_commit"]

    # must be a 64-char sha256 content hash (NOT the 40-char git sha)
    expected = materialize._skill_dir_version(pool_dir / "billing")
    assert base_version is not None
    assert len(base_version) == 64
    assert all(c in "0123456789abcdef" for c in base_version)
    assert base_version == expected
    assert base_commit == sha


# ---------------------------------------------------------------------------
# 3.2: content-hash base_version → no false drift on upgrade
# ---------------------------------------------------------------------------


def test_no_false_drift_on_content_hash_base_version_upgrade(db, pool_dir, tmp_path, monkeypatch):
    """Upgrade scenario: existing content-hash base_version does NOT trigger false drift
    when the agent home copy has not actually changed.
    """
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha = _setup_pool_skill(pool_dir, "billing", "billing skill content")
    skill_admin_store.set_current_version("billing", sha)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")

    # Simulate a pre-upgrade base_version stored as a content-hash (64-hex, not 40)
    legacy_content_hash = "a" * 64
    skill_admin_store.set_base_version(agent.id, "billing", legacy_content_hash)

    # Run materialize — should NOT mark drift (home copy doesn't differ from pool)
    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    drift_row = skill_admin_store.get_drift(agent.id, "billing")
    assert drift_row["drift"] == 0, "must not be marked drifted after upgrade"

    # base_version must now be re-baselined to the content hash of the materialized skill dir
    expected = materialize._skill_dir_version(pool_dir / "billing")
    assert drift_row["base_version"] == expected


# ---------------------------------------------------------------------------
# 3.3: after re-baseline, drift detection uses git content comparison
# ---------------------------------------------------------------------------


def test_drift_detected_after_rebaseline_when_home_modified(db, pool_dir, tmp_path, monkeypatch):
    """After re-baseline, a subsequent materialize detects real drift when the
    agent's home copy was modified."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha = _setup_pool_skill(pool_dir, "crm-ops", "pool content")
    skill_admin_store.set_current_version("crm-ops", sha)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")

    # First materialize: writes git sha base_version
    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )
    home = materialize.home_dir(agent.name)

    # Simulate agent-side skill modification (drift)
    modified_skill = home / "skills" / "crm-ops" / "SKILL.md"
    assert modified_skill.exists()
    modified_skill.write_text(
        "---\nname: crm-ops\ndescription: test\n---\nmodified by agent", encoding="utf-8"
    )

    # Second materialize: should detect drift and NOT overwrite the modified copy
    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    drift_row = skill_admin_store.get_drift(agent.id, "crm-ops")
    assert drift_row["drift"] == 1, "modified home copy should be marked drifted"
    # Home file should still contain the modified content (not overwritten)
    assert "modified by agent" in modified_skill.read_text()


def test_materialize_refreshes_base_commit_for_clean_home_and_preserves_it_on_drift(
    db, pool_dir, tmp_path, monkeypatch
):
    """Clean homes refresh to the latest pool commit; drifted homes keep their prior base_commit."""
    from fleetent.platform.skill_management import pool_git

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha_v1 = _setup_pool_skill(pool_dir, "billing", "pool-v1")
    skill_admin_store.set_current_version("billing", sha_v1)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )
    row_v1 = skill_admin_store.get_drift(agent.id, "billing")
    assert row_v1["drift"] == 0
    assert row_v1["base_commit"] == sha_v1

    (pool_dir / "billing" / "SKILL.md").write_text(
        "---\nname: billing\ndescription: test\n---\npool-v2",
        encoding="utf-8",
    )
    sha_v2 = pool_git.commit_pool(
        pool_dir,
        message="billing v2",
        author="system <system@f>",
        skill_name="billing",
    )
    assert sha_v2 is not None

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )
    row_v2 = skill_admin_store.get_drift(agent.id, "billing")
    assert row_v2["drift"] == 0
    assert row_v2["base_commit"] == sha_v2

    home_skill = materialize.home_dir(agent.name) / "skills" / "billing" / "SKILL.md"
    home_skill.write_text(
        "---\nname: billing\ndescription: test\n---\nagent-local-drift",
        encoding="utf-8",
    )

    (pool_dir / "billing" / "SKILL.md").write_text(
        "---\nname: billing\ndescription: test\n---\npool-v3",
        encoding="utf-8",
    )
    sha_v3 = pool_git.commit_pool(
        pool_dir,
        message="billing v3",
        author="system <system@f>",
        skill_name="billing",
    )
    assert sha_v3 is not None

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )
    row_v3 = skill_admin_store.get_drift(agent.id, "billing")
    assert row_v3["drift"] == 1
    assert row_v3["base_commit"] == sha_v2
    assert "agent-local-drift" in home_skill.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3.4: copytree pool→agent home excludes .git
# ---------------------------------------------------------------------------


def test_copytree_excludes_git_directory(db, pool_dir, tmp_path, monkeypatch):
    """The agent home skills directory must NOT contain a .git directory."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha = _setup_pool_skill(pool_dir, "billing", "billing skill content")
    skill_admin_store.set_current_version("billing", sha)

    assert (pool_dir / ".git").is_dir(), "pool must have .git for this test to be meaningful"

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    home = materialize.home_dir(agent.name)
    skills_home = home / "skills"

    # .git must not be copied into agent home skills dir
    assert not (skills_home / ".git").exists(), ".git must not appear in agent home skills"
    # The skill itself must be present
    assert (skills_home / "billing").is_dir()


# ---------------------------------------------------------------------------
# Task 6 (skill-gitops-subdir): _copy_skills resolves base_commit via git root
# + subdir when an external-git skills_subdir is configured (R2/R4).
# ---------------------------------------------------------------------------


def test_copy_skills_resolves_base_commit_via_git_root_when_subdir_configured(
    db, tmp_path, monkeypatch
):
    """R4: the scan root (no ``.git`` of its own) stays the copytree source; only the
    ``pool_version_for_skill`` lookup must be redirected to the git root + subdir.
    """
    from fleetent.platform.skill_management import git_source_store, pool_git

    git_root = tmp_path / "ai-skills-library"
    scan_root = git_root / "skills"
    sha = _setup_subdir_pool_skill(git_root, "skills", "incident-review", "body v1")

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(scan_root))
    git_source_store.set_config(
        enabled=1,
        remote_url="https://example.test/repo.git",
        branch="main",
        skills_subdir="skills",
    )
    skill_admin_store.set_current_version("incident-review", sha)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "incident-review", True, updated_by="admin")

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    home = materialize.home_dir(agent.name)
    skills_home = home / "skills"

    # R4: only the real skill dir is copied — no .git, no sibling monorepo dirs.
    assert (skills_home / "incident-review").is_dir()
    assert not (skills_home / ".git").exists()
    assert sorted(p.name for p in skills_home.iterdir()) == ["incident-review"]

    drift_row = skill_admin_store.get_drift(agent.id, "incident-review")
    base_commit = drift_row["base_commit"]

    # Independent oracle: compute the expected sha directly against the git root,
    # bypassing the production code path under test.
    expected = pool_git.pool_version_for_skill(git_root, "incident-review", subdir="skills")
    assert expected == sha
    assert base_commit == expected

    # R2 cross-check: simulate what node_desired_state_api._skill_manifests_for computes
    # for the same skill under the same config — the two call sites must agree exactly.
    node_side_git_root = pool_git.resolve_git_root(scan_root, "skills")
    node_side_commit = pool_git.pool_version_for_skill(
        node_side_git_root, "incident-review", subdir="skills"
    )
    assert node_side_git_root == git_root
    assert node_side_commit == base_commit


def test_copy_skills_base_commit_unchanged_when_no_external_git_source_configured(
    db, pool_dir, tmp_path, monkeypatch
):
    """Backward compatibility: with no external git source configured, base_commit
    resolution is unaffected — byte-for-byte identical to the pre-existing behavior.
    """
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha = _setup_pool_skill(pool_dir, "billing", "billing skill content")
    skill_admin_store.set_current_version("billing", sha)

    agent = _create_agent(db)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")

    materialize.write_home(
        materialize.agent_file_from_store(agent),
        source_agent=agent,
    )

    drift_row = skill_admin_store.get_drift(agent.id, "billing")
    assert drift_row["base_commit"] == sha
