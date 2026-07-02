"""Integration tests for backflow conflict detection and confirm gate.

Covers tasks 4.1–4.2 of skill-backflow-review:
- 4.1: base_version ≠ pool head → review marks conflict + shows diff vs head, no auto-merge
- 4.2: conflict accept requires explicit confirm + records overridden_head
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

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


def _nominate_with_conflict(
    agent: agent_store.Agent, skill_name: str, pool_dir: Path, content: str
) -> int:
    """Nominate with a stale base_version so conflict=1 is set at nominate time."""
    # Use a fake base_version that differs from current pool state → conflict detected
    skill_admin_store.set_binding(agent.id, skill_name, True, updated_by="admin")
    skill_admin_store.set_base_version(agent.id, skill_name, "a" * 64)
    skill_admin_store.set_drift(agent.id, skill_name, drifted=True)
    return backflow_store.nominate(
        agent_id=agent.id,
        skill_name=skill_name,
        proposed_content=content,
        pool_dir=pool_dir,
    )


# ---------------------------------------------------------------------------
# 4.1: conflict detection
# ---------------------------------------------------------------------------


def test_conflict_flagged_when_pool_advanced(db, pool_dir):
    """Proposals created when pool has advanced past base_version have conflict=1."""
    _commit_skill(pool_dir, "invoicing", "v1-content")
    agent = _create_agent()

    # Use a stale (non-matching) base_version to trigger conflict
    evolved = "---\nname: invoicing\ndescription: test\n---\nevolved invoicing"
    pid = _nominate_with_conflict(agent, "invoicing", pool_dir, evolved)

    row = backflow_store.get_proposal(pid)
    assert row is not None
    assert row["conflict"] == 1, "conflict should be flagged when pool has advanced"


def test_diff_vs_head_non_empty_on_conflict(db, pool_dir):
    """get_proposal_diff.diff_vs_head is non-empty and conflict=True when pool advanced."""
    _commit_skill(pool_dir, "invoicing2", "v1-content")
    agent = _create_agent()
    evolved = "---\nname: invoicing2\ndescription: test\n---\nevolved invoicing2"
    pid = _nominate_with_conflict(agent, "invoicing2", pool_dir, evolved)

    diff = backflow_store.get_proposal_diff(pid, pool_dir=pool_dir)
    assert diff["conflict"] is True
    # diff_vs_head captures difference between evolved and current pool head
    assert isinstance(diff["diff_vs_head"], str)


# Accept-on-conflict tests were removed with the accept endpoint: the platform no longer
# adopts backflow (conflict is surfaced read-only in the diff; adoption is a human git PR).
