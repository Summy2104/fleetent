"""Integration tests for drift-triggered automatic backflow nomination.

When a node status report flips a skill to drifted, the platform should
auto-create a pending backflow proposal (deduped), best-effort.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fleetent import agent_store
from fleetent.platform.skill_management import backflow_store, skill_admin_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    from fleetent.platform.skill_management.pool_git import init_pool

    d = tmp_path / "pool"
    d.mkdir()
    init_pool(d)
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(d))
    return d


@pytest.fixture
def node_client(db) -> TestClient:
    from fleetent.platform.node_management import node_desired_state_api

    app = FastAPI()
    app.include_router(node_desired_state_api.router)
    return TestClient(app)


def _setup_drifted_agent(pool_dir: Path, skill_name: str = "crm-ops") -> agent_store.Agent:
    """Commit a pool skill, bind+materialize it for an agent, and evolve the home copy.

    Leaves drift UNSET — the status POST is what marks drift in these tests.
    """
    from fleetent.platform.agent_lifecycle import materialize
    from fleetent.platform.skill_management.pool_git import commit_pool

    skill_dir = pool_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: test\n---\npool v1\n", encoding="utf-8"
    )
    commit_pool(pool_dir, message=f"add {skill_name}", author="admin <a@a>", skill_name=skill_name)

    tenancy_store.create_tenant(id="acme", name="Acme")
    agent = agent_store.create_agent("support", "p", [], tenant_id="acme")
    skill_admin_store.set_binding(agent.id, skill_name, True, updated_by="admin")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    home_skill = materialize.home_dir(agent.name) / "skills" / skill_name
    (home_skill / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: test\n---\nevolved by agent\n", encoding="utf-8"
    )
    return agent


def _post_status(client: TestClient, node_key: str, agent_id: int, *, drift: bool) -> object:
    return client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "agents": [
                {
                    "agent_id": agent_id,
                    "phase": "running",
                    "skills": [
                        {
                            "skill_name": "crm-ops",
                            "base_version": "base-v1",
                            "base_commit": "commit-1",
                            "drift": drift,
                        }
                    ],
                }
            ]
        },
    )


def test_status_drift_auto_creates_pending_proposal(node_client, db, pool_dir):
    from fleetent.platform.node_management import node_store

    agent = _setup_drifted_agent(pool_dir)
    node_key, _ = node_store.register_node("node-a")

    resp = _post_status(node_client, node_key, agent.id, drift=True)

    assert resp.status_code == 200
    assert skill_admin_store.get_drift(agent.id, "crm-ops")["drift"] == 1
    pending = backflow_store.list_proposals(
        agent_id=agent.id, skill_name="crm-ops", status="pending"
    )
    assert len(pending) == 1
    assert pending[0]["proposed_bundle"]


def test_status_drift_is_deduped(node_client, db, pool_dir):
    from fleetent.platform.node_management import node_store

    agent = _setup_drifted_agent(pool_dir)
    node_key, _ = node_store.register_node("node-a")

    assert _post_status(node_client, node_key, agent.id, drift=True).status_code == 200
    assert _post_status(node_client, node_key, agent.id, drift=True).status_code == 200

    pending = backflow_store.list_proposals(
        agent_id=agent.id, skill_name="crm-ops", status="pending"
    )
    assert len(pending) == 1


def test_status_no_drift_creates_no_proposal(node_client, db, pool_dir):
    from fleetent.platform.node_management import node_store

    agent = _setup_drifted_agent(pool_dir)
    node_key, _ = node_store.register_node("node-a")

    resp = _post_status(node_client, node_key, agent.id, drift=False)

    assert resp.status_code == 200
    pending = backflow_store.list_proposals(
        agent_id=agent.id, skill_name="crm-ops", status="pending"
    )
    assert pending == []


def test_nomination_failure_does_not_break_status(node_client, db, pool_dir, monkeypatch):
    from fleetent.platform.node_management import node_store

    agent = _setup_drifted_agent(pool_dir)
    node_key, _ = node_store.register_node("node-a")

    called: list[dict] = []

    def boom(**kwargs):
        called.append(kwargs)
        raise RuntimeError("nominate boom")

    monkeypatch.setattr(backflow_store, "nominate_if_absent", boom, raising=False)

    resp = _post_status(node_client, node_key, agent.id, drift=True)

    assert resp.status_code == 200
    assert called  # auto-nominate must have been attempted
    assert skill_admin_store.get_drift(agent.id, "crm-ops")["drift"] == 1
