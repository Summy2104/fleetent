"""Integration tests for backflow_proposals: nomination and storage.

Covers task 1.1 of skill-backflow-review:
- nominating a drifted skill creates a pending proposal (1.1)
- nominating a non-drifted skill is rejected (1.1)
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
    d = tmp_path / "pool"
    d.mkdir()
    return d


def _create_agent(name: str = "support") -> agent_store.Agent:
    tenancy_store.create_tenant(id="acme", name="Acme")
    return agent_store.create_agent(name, "You are support.", [], tenant_id="acme")


def _setup_pool_skill(pool_dir: Path, name: str, content: str) -> None:
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )


_FAKE_BASE = "a" * 64  # 64-char content hash (sha256 format)


def test_nominate_drifted_skill_creates_pending_proposal(db, pool_dir, monkeypatch):
    """Nominating a drifted agent skill creates a pending backflow_proposals row."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _setup_pool_skill(pool_dir, "crm-ops", "pool-v1")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, "crm-ops", _FAKE_BASE)
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    evolved = "---\nname: crm-ops\ndescription: test\n---\nevolved by agent"
    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="crm-ops",
        proposed_content=evolved,
        pool_dir=pool_dir,
    )

    assert proposal_id is not None and proposal_id > 0
    row = backflow_store.get_proposal(proposal_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["agent_id"] == agent.id
    assert row["skill_name"] == "crm-ops"
    assert row["proposed_content"] == evolved
    assert row["base_version"] == _FAKE_BASE


def test_nominate_non_drifted_skill_raises(db, pool_dir, monkeypatch):
    """Nominating a non-drifted skill raises ValueError."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _setup_pool_skill(pool_dir, "billing", "pool content")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")
    # drift stays 0 (default)

    with pytest.raises(ValueError, match="not drifted"):
        backflow_store.nominate(
            agent_id=agent.id,
            skill_name="billing",
            proposed_content="some evolved content",
            pool_dir=pool_dir,
        )


def test_list_pending_proposals(db, pool_dir, monkeypatch):
    """list_proposals returns only pending proposals for the given skill."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _setup_pool_skill(pool_dir, "crm-ops", "pool-v1")
    tenancy_store.create_tenant(id="acme", name="Acme")
    agent1 = agent_store.create_agent("bot1", "p", [], tenant_id="acme")
    agent2 = agent_store.create_agent("bot2", "p", [], tenant_id="acme")

    for agent in (agent1, agent2):
        skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
        skill_admin_store.set_base_version(agent.id, "crm-ops", _FAKE_BASE)
        skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)
        backflow_store.nominate(
            agent_id=agent.id,
            skill_name="crm-ops",
            proposed_content=f"evolved by {agent.name}",
            pool_dir=pool_dir,
        )

    rows = backflow_store.list_proposals(skill_name="crm-ops", status="pending")
    assert len(rows) == 2
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["skill_name"] == "crm-ops" for r in rows)
