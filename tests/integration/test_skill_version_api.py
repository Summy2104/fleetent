"""Integration tests for skill version history and diff API endpoints.

Covers tasks 4.1–4.2 of skill-pool-git-versioning:
- GET /admin/skills/{name}/versions returns commit history (4.1)
- GET /admin/skills/{name}/versions/{ref}/diff returns text diff; large diff degrades (4.2)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fleetent import auth, user_store
from fleetent.platform.skill_management import pool_git, skill_admin_api
from fleetent.platform.skill_management.skill_admin_api import router
from tests.integration._migration_template import apply_migrations


# ---------------------------------------------------------------------------
# App + auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    from fastapi import FastAPI

    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def admin_token(db):
    user, _ = user_store.create_user("alice")
    user_store.set_role(user.id, "admin")
    return auth.create_session(user.id)


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    d = tmp_path / "pool"
    d.mkdir()
    return d


def _add_skill(pool_dir: Path, name: str, content: str) -> str:
    pool_git.init_pool(pool_dir)
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{content}", encoding="utf-8"
    )
    sha = pool_git.commit_pool(
        pool_dir, message=f"edit: {name}", author="admin <a@a.com>", skill_name=name
    )
    assert sha is not None
    return sha


# ---------------------------------------------------------------------------
# 4.1: GET /admin/skills/{name}/versions
# ---------------------------------------------------------------------------


def test_skill_versions_returns_history(app, db, admin_token, pool_dir, monkeypatch):
    """History endpoint returns commits in reverse chronological order."""
    monkeypatch.setattr(skill_admin_api, "engine_skills_dir", lambda: str(pool_dir))

    sha1 = _add_skill(pool_dir, "crm-ops", "v1 content")
    # edit again
    (pool_dir / "crm-ops" / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: test\n---\nv2 content", encoding="utf-8"
    )
    sha2 = pool_git.commit_pool(
        pool_dir, message="edit: crm-ops v2", author="admin <a@a.com>", skill_name="crm-ops"
    )
    assert sha2 is not None

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get(
        "/admin/skills/crm-ops/versions",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert resp.status_code == 200
    versions = resp.json()
    assert isinstance(versions, list)
    assert len(versions) >= 2

    # Must have sha, message, author, timestamp fields
    entry = versions[0]
    assert "sha" in entry
    assert "message" in entry
    assert "author" in entry
    assert "timestamp" in entry

    # Most recent first
    assert versions[0]["sha"] == sha2
    assert versions[1]["sha"] == sha1


def test_skill_versions_requires_auth(app, db, pool_dir, monkeypatch):
    monkeypatch.setattr(skill_admin_api, "engine_skills_dir", lambda: str(pool_dir))
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/admin/skills/crm-ops/versions")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4.2: GET /admin/skills/{name}/versions/{ref}/diff
# ---------------------------------------------------------------------------


def test_skill_version_diff_returns_text(app, db, admin_token, pool_dir, monkeypatch):
    """Diff endpoint returns text diff for a specific commit ref."""
    monkeypatch.setattr(skill_admin_api, "engine_skills_dir", lambda: str(pool_dir))

    sha1 = _add_skill(pool_dir, "billing", "v1 content")
    (pool_dir / "billing" / "SKILL.md").write_text(
        "---\nname: billing\ndescription: test\n---\nv2 content", encoding="utf-8"
    )
    sha2 = pool_git.commit_pool(
        pool_dir, message="edit: billing v2", author="admin <a@a.com>", skill_name="billing"
    )
    assert sha2 is not None

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get(
        f"/admin/skills/billing/versions/{sha2}/diff",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "diff" in data
    assert "truncated" in data
    assert data["truncated"] is False
    assert "v2 content" in data["diff"] or "v1 content" in data["diff"]


def test_skill_version_diff_large_degrades_to_file_list(
    app, db, admin_token, pool_dir, monkeypatch
):
    """A diff that exceeds the size limit degrades to changed file list, never silently truncates."""
    import fleetent.platform.skill_management.pool_git as pg_mod

    monkeypatch.setattr(skill_admin_api, "engine_skills_dir", lambda: str(pool_dir))
    # Temporarily lower the limit to force degradation
    original_limit = pg_mod._DIFF_SIZE_LIMIT
    monkeypatch.setattr(pg_mod, "_DIFF_SIZE_LIMIT", 10)

    sha = _add_skill(pool_dir, "heavy-skill", "some content")

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get(
        f"/admin/skills/heavy-skill/versions/{sha}/diff",
        headers={"Authorization": f"Session {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["truncated"] is True
    assert "changed_files" in data
    assert isinstance(data["changed_files"], list)
    assert "warning" in data
    # diff must be empty (not silently truncated)
    assert data["diff"] == ""
