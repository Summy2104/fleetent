"""Integration tests for backflow diff computation."""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent import agent_store
from fleetent.platform.skill_management import backflow_store, skill_admin_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def pool_dir(tmp_path):
    from fleetent.platform.skill_management.pool_git import init_pool

    d = tmp_path / "pool"
    d.mkdir()
    init_pool(d)
    return d


def _create_agent() -> agent_store.Agent:
    tenancy_store.create_tenant(id="acme", name="Acme")
    return agent_store.create_agent("support", "p", [], tenant_id="acme")


def _commit_skill(pool_dir: Path, name: str, content: str) -> str:
    from fleetent.platform.skill_management.pool_git import commit_pool

    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    sha = commit_pool(pool_dir, message=f"add {name}", author="admin <a@a>", skill_name=name)
    assert sha is not None
    # Mirror production's commit -> reconcile: current_version (read as base_commit on the
    # materialize hot path, and the ref diff_vs_base reconstructs from) is set by the
    # post-sync reconcile, not commit_pool. Seed it so the diff has a base to reconstruct.
    skill_admin_store.set_current_version(name, sha)
    return sha


def test_diff_vs_base_shows_real_line_delta(db, pool_dir, monkeypatch):
    """diff_vs_base must reconstruct the base from base_commit, not treat base_version as a ref."""
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "crm-ops", "line one\nline two old\nline three")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    home = materialize.home_dir(agent.name)
    evolved_path = home / "skills" / "crm-ops" / "SKILL.md"
    evolved_path.write_text(
        (
            "---\nname: crm-ops\ndescription: test\n---\n"
            "line one\nline two new\nline three\nline four added"
        ),
        encoding="utf-8",
    )
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="crm-ops",
        pool_dir=pool_dir,
    )

    diff = backflow_store.get_proposal_diff(proposal_id, pool_dir=pool_dir)
    assert diff["diff_vs_base"]
    assert "--- base/SKILL.md" in diff["diff_vs_base"]
    assert "-line two old" in diff["diff_vs_base"]
    assert "+line two new" in diff["diff_vs_base"]
    assert "+line four added" in diff["diff_vs_base"]


def test_diff_vs_base_gracefully_degrades_when_base_commit_missing(db, pool_dir, monkeypatch):
    """Proposals without base_commit should not error or misreport the whole file as all-new."""
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "billing", "pool-v1")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    skill_admin_store.set_base_commit(agent.id, "billing", None)

    evolved_path = materialize.home_dir(agent.name) / "skills" / "billing" / "SKILL.md"
    evolved_path.write_text(
        "---\nname: billing\ndescription: test\n---\nevolved billing",
        encoding="utf-8",
    )
    skill_admin_store.set_drift(agent.id, "billing", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="billing",
        pool_dir=pool_dir,
    )
    diff = backflow_store.get_proposal_diff(proposal_id, pool_dir=pool_dir)

    assert "base unknown" in diff["diff_vs_base"].lower()
    assert "evolved billing" in diff["diff_vs_head"]


def test_diff_vs_head_and_conflict_still_reflect_pool_head(db, pool_dir, monkeypatch):
    """diff_vs_head and conflict detection continue to compare against the current pool head."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "search", "pool-v1")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "search", True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, "search", "a" * 64)
    skill_admin_store.set_base_commit(agent.id, "search", None)
    skill_admin_store.set_drift(agent.id, "search", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="search",
        proposed_content="---\nname: search\ndescription: test\n---\nevolved search",
        pool_dir=pool_dir,
    )

    (pool_dir / "search" / "SKILL.md").write_text(
        "---\nname: search\ndescription: test\n---\npool-v2",
        encoding="utf-8",
    )
    from fleetent.platform.skill_management.pool_git import commit_pool

    commit_pool(pool_dir, message="edit search v2", author="admin <a@a>", skill_name="search")

    diff = backflow_store.get_proposal_diff(proposal_id, pool_dir=pool_dir)
    assert diff["conflict"] is True
    assert "pool-v2" in diff["diff_vs_head"]


def test_diff_with_subdir_reads_base_from_git_root_head_from_scan_root(db, tmp_path, monkeypatch):
    """With skills_subdir configured, git_root and scan root are different directories.

    diff_vs_base must reconstruct base content from the git tree at ``skills/<name>``
    (git root + subdir), while diff_vs_head / conflict must keep reading the real current
    files under the scan root (``<git_root>/skills/<name>``). A mix-up that routed the
    filesystem reads to the git root would fail here because ``<git_root>/<name>`` does not
    exist (real files live one level deeper under ``skills/``).
    """
    from fleetent.platform.skill_management.pool_git import commit_pool, init_pool

    git_root = tmp_path / "repo"
    git_root.mkdir()
    init_pool(git_root)
    scan_root = git_root / "skills"  # genuinely different directory from git_root
    scan_root.mkdir()

    # Commit the base content under the subdir tree path (skills/crm-ops).
    skill_dir = scan_root / "crm-ops"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: test\n---\nline one\nline two old\nline three",
        encoding="utf-8",
    )
    base_commit = commit_pool(
        git_root,
        message="add crm-ops",
        author="admin <a@a>",
        skill_name="crm-ops",
        subdir="skills",
    )
    assert base_commit is not None

    # Compute base_version as the scan-root content hash so conflict detection is meaningful.
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(scan_root))
    agent = _create_agent()
    from fleetent.platform.skill_management import bundle_cache

    base_version = bundle_cache.skill_directory_version(skill_dir)
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, "crm-ops", base_version)
    skill_admin_store.set_base_commit(agent.id, "crm-ops", base_commit)
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="crm-ops",
        proposed_content=(
            "---\nname: crm-ops\ndescription: test\n---\n"
            "line one\nline two new\nline three\nline four added"
        ),
        pool_dir=scan_root,
    )

    # Advance the pool head under the scan root so conflict detection has something to see.
    (skill_dir / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: test\n---\nline one\nline two old\nline three\npool-v2",
        encoding="utf-8",
    )
    commit_pool(
        git_root,
        message="edit crm-ops v2",
        author="admin <a@a>",
        skill_name="crm-ops",
        subdir="skills",
    )

    diff = backflow_store.get_proposal_diff(
        proposal_id, pool_dir=scan_root, git_root=git_root, subdir="skills"
    )

    # diff_vs_base proves pool_bundle_at found base content via the subdir git tree path.
    assert diff["diff_vs_base"]
    assert "-line two old" in diff["diff_vs_base"]
    assert "+line two new" in diff["diff_vs_base"]
    assert "+line four added" in diff["diff_vs_base"]
    # diff_vs_head / conflict prove the filesystem reads stayed on the scan root.
    assert diff["conflict"] is True
    assert "pool-v2" in diff["diff_vs_head"]
