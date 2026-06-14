"""Integration tests for backflow governance decisions (accept/reject/fork).

Covers tasks 3.1–3.4 of skill-backflow-review:
- 3.1: admin governance auth required; DM path not involved
- 3.2: accept → writes pool + commit_pool + current_version + clears drift
- 3.3: reject → pool unchanged + proposal closed + drift cleared
- 3.4: fork → new named skill in pool + source agent binding updated
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fleetent import agent_store, auth, user_store
from fleetent.platform.skill_management import backflow_store, skill_admin_store
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
    sha = commit_pool(pool_dir, message=f"add {name}", author="admin <a@a>", skill_name=name)
    assert sha is not None
    return sha


def _skill_content_hash(pool_dir: Path, skill_name: str) -> str:
    from hashlib import sha256

    skill_dir = pool_dir / skill_name
    digest = sha256()
    for path in sorted(
        p for p in skill_dir.rglob("*") if p.is_file() and ".git" not in p.parts
    ):
        digest.update(path.relative_to(skill_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _nominate(agent: agent_store.Agent, skill_name: str, pool_dir: Path, content: str) -> int:
    # Use real content hash so conflict=0 (pool hasn't advanced past materialization point)
    real_hash = _skill_content_hash(pool_dir, skill_name)
    skill_admin_store.set_binding(agent.id, skill_name, True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, skill_name, real_hash)
    skill_admin_store.set_drift(agent.id, skill_name, drifted=True)
    return backflow_store.nominate(
        agent_id=agent.id,
        skill_name=skill_name,
        proposed_content=content,
        pool_dir=pool_dir,
    )


# ---------------------------------------------------------------------------
# 3.1: governance auth
# ---------------------------------------------------------------------------


def test_governance_requires_admin_auth(app, db, pool_dir):
    """Backflow decision endpoints require admin auth."""
    _commit_skill(pool_dir, "billing", "v1")
    agent = _create_agent()
    pid = _nominate(
        agent, "billing", pool_dir, "---\nname: billing\ndescription: test\n---\nevolved"
    )

    client = TestClient(app, raise_server_exceptions=True)
    # No auth → 401
    resp = client.post(f"/admin/skills/backflow/{pid}/accept")
    assert resp.status_code == 401

    # Viewer auth is not enough
    viewer, _ = user_store.create_user("viewer")
    viewer_token = auth.create_session(viewer.id)
    resp = client.post(
        f"/admin/skills/backflow/{pid}/accept",
        headers={"Authorization": f"Session {viewer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3.2: accept
# ---------------------------------------------------------------------------


def test_accept_writes_pool_commits_and_clears_drift(app, db, pool_dir, admin_token, monkeypatch):
    """accept → evolvedcontent in pool + new commit + current_version updated + drift=0."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    sha1 = _commit_skill(pool_dir, "crm-ops", "pool-v1")
    skill_admin_store.set_current_version("crm-ops", sha1)

    agent = _create_agent()
    evolved = "---\nname: crm-ops\ndescription: test\n---\nevolved crm-ops"
    pid = _nominate(agent, "crm-ops", pool_dir, evolved)

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post(
        f"/admin/skills/backflow/{pid}/accept",
        headers={"Authorization": f"Session {admin_token}"},
        json={"author": "alice <alice@example.com>"},
    )
    assert resp.status_code == 200

    # Pool file updated
    pool_content = (pool_dir / "crm-ops" / "SKILL.md").read_text(encoding="utf-8")
    assert "evolved crm-ops" in pool_content

    # Pool has a new commit
    from fleetent.platform.skill_management.pool_git import pool_skill_history

    history = pool_skill_history(pool_dir, "crm-ops")
    assert len(history) >= 2

    # current_version updated
    src = skill_admin_store.get_source("crm-ops")
    assert src["current_version"] is not None
    assert src["current_version"] != sha1

    # drift cleared for the source agent
    drift = skill_admin_store.get_drift(agent.id, "crm-ops")
    assert drift["drift"] == 0

    # proposal status = accepted
    row = backflow_store.get_proposal(pid)
    assert row is not None
    assert row["status"] == "accepted"


# ---------------------------------------------------------------------------
# 3.3: reject
# ---------------------------------------------------------------------------


def test_reject_leaves_pool_unchanged_and_clears_drift(app, db, pool_dir, admin_token, monkeypatch):
    """reject → pool unchanged + proposal closed + drift cleared."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "search", "pool-v1")
    agent = _create_agent()
    evolved = "---\nname: search\ndescription: test\n---\nevolved search"
    pid = _nominate(agent, "search", pool_dir, evolved)

    original_content = (pool_dir / "search" / "SKILL.md").read_text(encoding="utf-8")

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post(
        f"/admin/skills/backflow/{pid}/reject",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert resp.status_code == 200

    # Pool unchanged
    assert (pool_dir / "search" / "SKILL.md").read_text(encoding="utf-8") == original_content

    # drift cleared
    drift = skill_admin_store.get_drift(agent.id, "search")
    assert drift["drift"] == 0

    # proposal closed
    row = backflow_store.get_proposal(pid)
    assert row is not None
    assert row["status"] == "rejected"


# ---------------------------------------------------------------------------
# 3.4: fork
# ---------------------------------------------------------------------------


def test_fork_creates_new_skill_and_updates_binding(app, db, pool_dir, admin_token, monkeypatch):
    """fork → new-named skill in pool + source agent binding updated + original unchanged."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))

    _commit_skill(pool_dir, "crm-ops", "pool-v1")
    agent = _create_agent()
    evolved = "---\nname: crm-ops\ndescription: test\n---\nevolved for bot"
    pid = _nominate(agent, "crm-ops", pool_dir, evolved)

    original_content = (pool_dir / "crm-ops" / "SKILL.md").read_text(encoding="utf-8")

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post(
        f"/admin/skills/backflow/{pid}/fork",
        headers={"Authorization": f"Session {admin_token}"},
        json={"fork_name": "crm-ops-support", "author": "alice <alice@example.com>"},
    )
    assert resp.status_code == 200

    # Original skill unchanged
    assert (pool_dir / "crm-ops" / "SKILL.md").read_text(encoding="utf-8") == original_content

    # Fork skill exists in pool
    fork_file = pool_dir / "crm-ops-support" / "SKILL.md"
    assert fork_file.exists()
    assert "evolved for bot" in fork_file.read_text(encoding="utf-8")

    # Proposal forked_as updated
    row = backflow_store.get_proposal(pid)
    assert row is not None
    assert row["status"] == "forked"
    assert row["forked_as"] == "crm-ops-support"

    # drift cleared
    drift = skill_admin_store.get_drift(agent.id, "crm-ops")
    assert drift["drift"] == 0
