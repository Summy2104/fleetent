"""Integration tests for backflow governance decisions (accept/reject/fork)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fleetent import agent_store, auth, user_store
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


@pytest.fixture
def app(pool_dir, monkeypatch):
    from fleetent.platform.skill_management import backflow_api

    monkeypatch.setattr(backflow_api, "engine_skills_dir", lambda: str(pool_dir))
    application = FastAPI()
    application.include_router(backflow_api.router)
    return application


@pytest.fixture
def admin_token(db):
    user, _ = user_store.create_user("alice")
    user_store.set_role(user.id, "admin")
    return auth.create_session(user.id)


def _create_agent(name: str = "support") -> agent_store.Agent:
    tenancy_store.create_tenant(id="acme", name="Acme")
    return agent_store.create_agent(name, "p", [], tenant_id="acme")


def _commit_skill(pool_dir: Path, name: str, content: str) -> str:
    from fleetent.platform.skill_management.pool_git import commit_pool

    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "sync.py").write_text("print('pool script')\n", encoding="utf-8")
    obsolete_dir = skill_dir / "obsolete"
    obsolete_dir.mkdir(exist_ok=True)
    (obsolete_dir / "old.txt").write_text("legacy\n", encoding="utf-8")
    sha = commit_pool(pool_dir, message=f"add {name}", author="admin <a@a>", skill_name=name)
    assert sha is not None
    return sha


def _nominate(
    agent: agent_store.Agent,
    skill_name: str,
    pool_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))
    skill_admin_store.set_binding(agent.id, skill_name, True, updated_by="admin")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    home_skill = materialize.home_dir(agent.name) / "skills" / skill_name
    (home_skill / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: test\n---\nevolved {skill_name}",
        encoding="utf-8",
    )
    (home_skill / "scripts" / "sync.py").write_text("print('agent script')\n", encoding="utf-8")
    obsolete = home_skill / "obsolete" / "old.txt"
    if obsolete.exists():
        obsolete.unlink()
    skill_admin_store.set_drift(agent.id, skill_name, drifted=True)
    return backflow_store.nominate(agent_id=agent.id, skill_name=skill_name, pool_dir=pool_dir)


def test_list_backflow_returns_pending_metadata_without_bundle(
    app, db, pool_dir, admin_token, monkeypatch
):
    """GET /admin/skills/backflow lists pending proposals (admin-only, no bundle)."""
    _commit_skill(pool_dir, "billing", "v1")
    agent = _create_agent()
    pid = _nominate(agent, "billing", pool_dir, monkeypatch)

    client = TestClient(app, raise_server_exceptions=True)

    assert client.get("/admin/skills/backflow").status_code == 401

    viewer, _ = user_store.create_user("viewer")
    viewer_token = auth.create_session(viewer.id)
    assert (
        client.get(
            "/admin/skills/backflow", headers={"Authorization": f"Session {viewer_token}"}
        ).status_code
        == 403
    )

    resp = client.get("/admin/skills/backflow", headers={"Authorization": f"Session {admin_token}"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == pid
    assert item["status"] == "pending"
    assert item["agent_id"] == agent.id
    assert item["agent_name"] == agent.name
    assert item["skill_name"] == "billing"
    assert "conflict" in item
    assert "created_at" in item
    assert "proposed_bundle" not in item


def test_backflow_diff_returns_dual_diff_and_404_for_missing(
    app, db, pool_dir, admin_token, monkeypatch
):
    """GET /admin/skills/backflow/{id}/diff returns vs-base/vs-head/conflict; 404 if absent."""
    _commit_skill(pool_dir, "search", "v1")
    agent = _create_agent()
    pid = _nominate(agent, "search", pool_dir, monkeypatch)

    client = TestClient(app, raise_server_exceptions=True)

    assert client.get(f"/admin/skills/backflow/{pid}/diff").status_code == 401

    resp = client.get(
        f"/admin/skills/backflow/{pid}/diff",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "diff_vs_base" in body
    assert "diff_vs_head" in body
    assert "conflict" in body

    missing = client.get(
        "/admin/skills/backflow/999999/diff",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert missing.status_code == 404


def test_skill_manifest_carries_resync_epoch(db, pool_dir, monkeypatch):
    """The desired-state skill manifest exposes resync_epoch so the node can act on it."""
    from fleetent.platform.node_management import node_desired_state_api as nds

    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))
    _commit_skill(pool_dir, "crm-ops", "pool-v1")
    tenancy_store.create_tenant(id="acme", name="Acme")
    agent = agent_store.create_agent("support", "p", ["crm-ops"], tenant_id="acme")
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by="admin")

    manifest = next(m for m in nds._skill_manifests_for("node-a", agent) if m["name"] == "crm-ops")
    assert manifest["resync_epoch"] == "0"

    skill_admin_store.bump_resync_epoch(agent.id, "crm-ops")
    manifest2 = next(m for m in nds._skill_manifests_for("node-a", agent) if m["name"] == "crm-ops")
    assert manifest2["resync_epoch"] == "1"
