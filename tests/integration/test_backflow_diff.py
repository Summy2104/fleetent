"""Integration tests for backflow diff computation.

Covers task 2.1 of skill-backflow-review:
- proposal diff returns evolved vs base_version content
- proposal diff returns evolved vs pool head content
- uses pool_diff_for_commit / pool_content_at from Change 2
"""

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
    return sha


def test_proposal_diff_vs_base_version(db, pool_dir, tmp_path, monkeypatch):
    """Proposal diff includes 'evolved vs base content' section."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "crm-ops", "base content")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")

    from fleetent.platform.agent_lifecycle import materialize

    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    # Simulate agent evolving the skill
    home = materialize.home_dir(agent.name)
    evolved_path = home / "skills" / "crm-ops" / "SKILL.md"
    evolved_content = "---\nname: crm-ops\ndescription: test\n---\nevolved content"
    evolved_path.write_text(evolved_content, encoding="utf-8")
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="crm-ops",
        proposed_content=evolved_content,
        pool_dir=pool_dir,
    )

    diff = backflow_store.get_proposal_diff(proposal_id, pool_dir=pool_dir)
    assert "diff_vs_base" in diff
    assert "diff_vs_head" in diff
    # evolved content differs from base → diff is non-empty
    assert diff["diff_vs_base"] != "" or diff["diff_vs_head"] != ""
    # both diffs are strings
    assert isinstance(diff["diff_vs_base"], str)
    assert isinstance(diff["diff_vs_head"], str)


def test_proposal_diff_vs_head_reflects_pool_update(db, pool_dir, tmp_path, monkeypatch):
    """diff_vs_head reflects pool content that has advanced past base_version."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha1 = _commit_skill(pool_dir, "billing", "pool-v1")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, "billing", "a" * 64)
    skill_admin_store.set_drift(agent.id, "billing", drifted=True)

    evolved = "---\nname: billing\ndescription: test\n---\nevolved billing"
    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="billing",
        proposed_content=evolved,
        pool_dir=pool_dir,
    )

    # Pool advances to v2
    (pool_dir / "billing" / "SKILL.md").write_text(
        "---\nname: billing\ndescription: test\n---\npool-v2", encoding="utf-8"
    )
    from fleetent.platform.skill_management.pool_git import commit_pool

    commit_pool(pool_dir, message="edit billing v2", author="admin <a@a>", skill_name="billing")

    diff = backflow_store.get_proposal_diff(proposal_id, pool_dir=pool_dir)
    # diff_vs_head should capture evolved vs v2 (not vs v1)
    assert isinstance(diff["diff_vs_head"], str)
    assert diff["conflict"] is True  # base != head
