"""Integration test: skill_admin_api content-write endpoints are read-only under GitOps.

When an external git source is configured+enabled (skill_git_source.enabled=1), the skill
content-write endpoints return 409; reads and ops endpoints stay available. When no source
is configured, writes are not blocked by the GitOps gate.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.skill_management.skill_admin_api as api
import fleetent.user_store as user_store
from fleetent.db import SQLiteDatabase
from fleetent.platform.skill_management import git_source_store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(api, "engine_list_skills", lambda: [])
    monkeypatch.setattr(api, "engine_audit", lambda content: {"verdict": "pass", "rules": []})
    monkeypatch.setattr(api, "engine_reload", lambda: {"ok": True})
    monkeypatch.setattr(api, "engine_set_global_disabled", lambda n, d: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def _admin_token() -> str:
    u, _ = user_store.create_user("admin-user")
    user_store.set_role(u.id, "admin")
    return auth.create_session(u.id)


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


def test_gitops_blocks_content_writes(client) -> None:
    git_source_store.set_config(enabled=1, remote_url="https://git.example/x.git")
    token = _admin_token()
    # no-body write endpoints: the GitOps gate fires before any 404/confirm handling
    assert client.delete("/admin/skills/s", headers=_hdr(token, confirm=True)).status_code == 409
    assert client.post("/admin/skills/s/restore", headers=_hdr(token)).status_code == 409
    assert (
        client.post("/admin/skills/s/force-publish", headers=_hdr(token, confirm=True)).status_code
        == 409
    )


def test_gitops_keeps_reads(client) -> None:
    git_source_store.set_config(enabled=1, remote_url="https://git.example/x.git")
    token = _admin_token()
    assert client.get("/admin/skills", headers=_hdr(token)).status_code == 200


def test_writes_not_gitops_blocked_when_disabled(client) -> None:
    # no external source configured -> the GitOps gate must not fire
    token = _admin_token()
    assert client.delete("/admin/skills/s", headers=_hdr(token, confirm=True)).status_code != 409
