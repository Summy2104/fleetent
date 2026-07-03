"""Integration tests for backflow_proposals: nomination and storage.

Covers task 1.1 of skill-backflow-review:
- nominating a drifted skill creates a pending proposal (1.1)
- nominating a non-drifted skill is rejected (1.1)
"""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

import httpx
import pytest
import respx

from fleetent import agent_store
from fleetent.platform.node_management import node_store, placement_store
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


def _create_agent(name: str = "support") -> agent_store.Agent:
    tenancy_store.create_tenant(id="acme", name="Acme")
    return agent_store.create_agent(name, "You are support.", [], tenant_id="acme")


def _setup_pool_skill(pool_dir: Path, name: str, content: str) -> str:
    from fleetent.platform.skill_management.pool_git import commit_pool

    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "sync.py").write_text("print('pool script')\n", encoding="utf-8")
    sha = commit_pool(pool_dir, message=f"add {name}", author="admin <a@a>", skill_name=name)
    assert sha is not None
    # Mirror production's commit -> reconcile: the catalog's current_version (read on the
    # materialize/nominate hot path as base_commit) is populated by the post-sync reconcile,
    # not by commit_pool itself. Seed it here so the test reflects that invariant.
    skill_admin_store.set_current_version(name, sha)
    return sha


def test_nominate_drifted_skill_creates_pending_proposal(db, pool_dir, monkeypatch):
    """Nominating a drifted multi-file skill captures the full bundle and base_commit."""
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    base_commit = _setup_pool_skill(pool_dir, "crm-ops", "pool-v1")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    home_skill = materialize.home_dir(agent.name) / "skills" / "crm-ops"
    (home_skill / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: test\n---\nevolved by agent",
        encoding="utf-8",
    )
    (home_skill / "scripts" / "sync.py").write_text("print('agent script')\n", encoding="utf-8")
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    proposal_id = backflow_store.nominate(
        agent_id=agent.id,
        skill_name="crm-ops",
        pool_dir=pool_dir,
    )

    assert proposal_id is not None and proposal_id > 0
    row = backflow_store.get_proposal(proposal_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["agent_id"] == agent.id
    assert row["skill_name"] == "crm-ops"
    assert row["proposed_bundle"] == {
        "SKILL.md": "---\nname: crm-ops\ndescription: test\n---\nevolved by agent",
        "scripts/sync.py": "print('agent script')\n",
    }
    assert row["base_version"] is not None
    assert row["base_commit"] == base_commit


def test_is_landed_true_when_pool_matches_proposed(db, pool_dir):
    # A proposal is "landed" once the pool's copy of the skill equals the agent's proposed copy
    # (i.e. the human merged the backflow branch and it synced back) — then it drops off the
    # worklist. _setup_pool_skill writes SKILL.md + scripts/sync.py for the skill.
    _setup_pool_skill(pool_dir, "crm-ops", "body-v1")
    pool_match = {
        "SKILL.md": "---\nname: crm-ops\ndescription: test\n---\nbody-v1",
        "scripts/sync.py": "print('pool script')\n",
    }
    assert backflow_store.is_landed({"skill_name": "crm-ops", "proposed_bundle": pool_match}, pool_dir)
    evolved = {**pool_match, "SKILL.md": pool_match["SKILL.md"] + "\nevolved"}
    assert not backflow_store.is_landed({"skill_name": "crm-ops", "proposed_bundle": evolved}, pool_dir)
    # pool has no copy of the skill -> not landed
    assert not backflow_store.is_landed({"skill_name": "ghost", "proposed_bundle": pool_match}, pool_dir)


def test_nominate_non_drifted_skill_raises(db, pool_dir, monkeypatch):
    """Nominating a non-drifted skill raises ValueError."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _setup_pool_skill(pool_dir, "billing", "pool content")
    agent = _create_agent()
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by="admin")
    # drift stays 0 (default)

    with pytest.raises(ValueError, match="not drifted"):
        backflow_store.nominate(agent_id=agent.id, skill_name="billing", pool_dir=pool_dir)


def test_list_pending_proposals(db, pool_dir, monkeypatch):
    """list_proposals returns only pending proposals for the given skill."""
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _setup_pool_skill(pool_dir, "crm-ops", "pool-v1")
    tenancy_store.create_tenant(id="acme", name="Acme")
    agent1 = agent_store.create_agent("bot1", "p", [], tenant_id="acme")
    agent2 = agent_store.create_agent("bot2", "p", [], tenant_id="acme")

    for agent in (agent1, agent2):
        skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
        materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
        skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)
        home_skill = materialize.home_dir(agent.name) / "skills" / "crm-ops" / "SKILL.md"
        home_skill.write_text(
            f"---\nname: crm-ops\ndescription: test\n---\nevolved by {agent.name}",
            encoding="utf-8",
        )
        backflow_store.nominate(agent_id=agent.id, skill_name="crm-ops", pool_dir=pool_dir)

    rows = backflow_store.list_proposals(skill_name="crm-ops", status="pending")
    assert len(rows) == 2
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["skill_name"] == "crm-ops" for r in rows)


@respx.mock
def test_nominate_managed_skill_pulls_bundle_from_owning_node(db, pool_dir, monkeypatch):
    from fleetent.platform.skill_management import skill_admin_store as skill_catalog_store

    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "forwarder.test")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"7" * 32).decode("ascii"),
    )
    _setup_pool_skill(pool_dir, "crm-ops", "pool-v1")
    agent = _create_agent()
    skill_catalog_store.set_source("crm-ops", "managed")
    node_key, _ = node_store.register_node("node-a")
    placement_store.pin_agent(agent.id, "node-a")
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, "crm-ops", "a" * 64)
    skill_admin_store.set_base_commit(agent.id, "crm-ops", "b" * 40)
    skill_admin_store.set_drift(agent.id, "crm-ops", drifted=True)

    bundle_bytes = io.BytesIO()
    with tarfile.open(fileobj=bundle_bytes, mode="w:gz") as archive:
        for path, content in {
            "crm-ops/SKILL.md": "---\nname: crm-ops\ndescription: test\n---\nevolved by node",
            "crm-ops/scripts/sync.py": "print('node script')\n",
        }.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    route = respx.get(
        "http://forwarder.test:8767/forward/agents/support/skills/crm-ops/bundle"
    ).mock(return_value=httpx.Response(200, content=bundle_bytes.getvalue()))

    proposal_id = backflow_store.nominate(
        agent_id=agent.id, skill_name="crm-ops", pool_dir=pool_dir
    )

    assert route.called
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {node_key}"
    row = backflow_store.get_proposal(proposal_id)
    assert row is not None
    assert row["proposed_bundle"] == {
        "SKILL.md": "---\nname: crm-ops\ndescription: test\n---\nevolved by node",
        "scripts/sync.py": "print('node script')\n",
    }
