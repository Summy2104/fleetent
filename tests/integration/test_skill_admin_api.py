"""Tests for skill_admin_api (the /admin/skills management face).

Engine / reflection / askit seams are monkeypatched so the tests exercise the
management behaviour (gating, reference protection, audit, role guards) rather
than engine semantics. Covers platform.md scenarios 47-57.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.skill_management.skill_admin_api as api
import fleetent.platform.skill_management.skill_admin_store as store
import fleetent.user_store as user_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    # neutral engine seams by default; individual tests override.
    monkeypatch.setattr(api, "engine_list_skills", lambda: [])
    monkeypatch.setattr(api, "engine_audit", lambda content: {"verdict": "pass", "rules": []})
    monkeypatch.setattr(api, "engine_reload", lambda: {"ok": True})
    monkeypatch.setattr(api, "engine_set_global_disabled", lambda n, d: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


_VALID = "---\nname: s\ndescription: a helpful summarizer\n---\nbody"


# --- auth / role guards (场景 57) ---------------------------------------------


def test_no_auth_401(client):
    assert client.get("/admin/skills").status_code == 401


def test_viewer_can_read(client):
    token, _ = _session_for("viewer")
    assert client.get("/admin/skills", headers=_hdr(token)).status_code == 200


def test_viewer_cannot_create(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/skills", headers=_hdr(token), json={"name": "s", "content": _VALID})
    assert r.status_code == 403
    assert store.get_state("s")["status"] == "active"  # nothing persisted as published


# --- upload gating (场景 47/48/49) -------------------------------------------


def test_upload_pass_publishes(client, monkeypatch):
    monkeypatch.setattr(api, "engine_audit", lambda content: {"verdict": "pass", "rules": []})
    reloaded = {"n": 0}
    monkeypatch.setattr(
        api, "engine_reload", lambda: reloaded.update(n=reloaded["n"] + 1) or {"ok": True}
    )
    token, uid = _session_for("admin")
    r = client.post("/admin/skills", headers=_hdr(token), json={"name": "s", "content": _VALID})
    assert r.status_code == 200
    assert r.json()["published"] is True
    assert store.get_state("s")["status"] == "active"
    assert reloaded["n"] == 1  # hot reload triggered
    assert any(a["action"] == "skill.create" for a in audit.search_audit())


def test_upload_rejected_quarantined(client, monkeypatch):
    monkeypatch.setattr(
        api, "engine_audit", lambda content: {"verdict": "rejected", "rules": ["os.system("]}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/skills", headers=_hdr(token), json={"name": "evil", "content": _VALID})
    assert r.status_code == 200
    assert r.json()["published"] is False
    assert "os.system(" in r.json()["rules"]
    assert store.get_state("evil")["status"] == "quarantined"


def test_upload_suspicious_published_but_flagged(client, monkeypatch):
    monkeypatch.setattr(
        api, "engine_audit", lambda content: {"verdict": "suspicious", "rules": ["eval("]}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/skills", headers=_hdr(token), json={"name": "s", "content": _VALID})
    assert r.json()["published"] is True
    assert store.get_state("s")["audit_verdict"] == "suspicious"


def test_upload_invalid_frontmatter_422(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/skills", headers=_hdr(token), json={"name": "s", "content": "no frontmatter"}
    )
    assert r.status_code == 422
    assert store.get_state("s")["audit_verdict"] is None  # not persisted


# --- edit re-audit + reload + drift ------------------------------------------


def test_edit_reaudits_and_reloads(client, monkeypatch):
    calls = {"reload": 0, "audit": 0}
    monkeypatch.setattr(
        api, "engine_reload", lambda: calls.update(reload=calls["reload"] + 1) or {"ok": True}
    )
    monkeypatch.setattr(
        api,
        "engine_audit",
        lambda c: calls.update(audit=calls["audit"] + 1) or {"verdict": "pass", "rules": []},
    )
    token, _ = _session_for("admin")
    r = client.put("/admin/skills/s", headers=_hdr(token), json={"content": _VALID})
    assert r.status_code == 200
    assert calls["audit"] == 1 and calls["reload"] == 1


def test_edit_managed_marks_drift(client, monkeypatch):
    store.set_provenance("s", "managed")
    token, _ = _session_for("admin")
    r = client.put("/admin/skills/s", headers=_hdr(token), json={"content": _VALID})
    assert r.json()["drift"] is True
    assert store.get_provenance("s")["drift"] == 1


# --- global enable / disable (场景 50) ---------------------------------------


def test_global_disable_then_enable(client, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "engine_set_global_disabled", lambda n, d: seen.append((n, d)))
    token, _ = _session_for("admin")
    client.post("/admin/skills/s/disable", headers=_hdr(token))
    assert store.get_state("s")["global_enabled"] == 0
    client.post("/admin/skills/s/enable", headers=_hdr(token))
    assert store.get_state("s")["global_enabled"] == 1
    assert (("s", True) in seen) and (("s", False) in seen)


# --- hot reload (场景 56) -----------------------------------------------------


def test_reload_success(client, monkeypatch):
    monkeypatch.setattr(api, "engine_reload", lambda: {"ok": True})
    token, _ = _session_for("admin")
    assert client.post("/admin/skills/reload", headers=_hdr(token)).status_code == 200


def test_reload_failure_keeps_old_and_warns(client, monkeypatch):
    monkeypatch.setattr(api, "engine_reload", lambda: {"ok": False, "error": "parse error"})
    token, _ = _session_for("admin")
    r = client.post("/admin/skills/reload", headers=_hdr(token))
    assert r.status_code == 503
    assert "parse error" in r.json()["detail"]


# --- archive + reference protection + restore (场景 52/53) -------------------


def test_archive_blocked_when_enabled_by_agent(client):
    store.set_binding("agent-x", "s", enabled=True, updated_by="admin")
    token, _ = _session_for("admin")
    r = client.delete("/admin/skills/s", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert "agent-x" in r.json()["detail"]["agents"]
    assert store.get_state("s")["status"] == "active"  # not archived


def test_archive_requires_confirm(client):
    token, _ = _session_for("admin")
    r = client.delete("/admin/skills/s", headers=_hdr(token, confirm=False))
    assert r.status_code == 428


def test_archive_then_restore(client):
    token, _ = _session_for("admin")
    assert client.delete("/admin/skills/s", headers=_hdr(token, confirm=True)).status_code == 200
    assert store.get_state("s")["status"] == "archived"
    assert client.post("/admin/skills/s/restore", headers=_hdr(token)).status_code == 200
    assert store.get_state("s")["status"] == "active"


# --- per-agent binding (场景 51) ---------------------------------------------


def test_per_agent_disable_only_that_agent(client):
    token, _ = _session_for("admin")
    client.put("/admin/skills/s/agents/agent-a", headers=_hdr(token), json={"enabled": True})
    client.put("/admin/skills/s/agents/agent-b", headers=_hdr(token), json={"enabled": False})
    enabling = store.agents_enabling("s")
    assert enabling == ["agent-a"]  # b disabled, a still enabled


# --- force publish ------------------------------------------------------------


def test_force_publish_requires_confirm(client):
    token, _ = _session_for("admin")
    assert client.post("/admin/skills/s/force-publish", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/skills/s/force-publish", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert store.get_state("s")["forced"] == 1


# --- proposal inbox (场景 54/55) ---------------------------------------------


def test_approve_proposal_applies_via_reflection(client, monkeypatch):
    applied = []
    monkeypatch.setattr(api, "reflection_apply_proposal", lambda pid: applied.append(pid))
    token, _ = _session_for("admin")
    r = client.post("/admin/skills/proposals/p1/approve", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert applied == ["p1"]
    assert any(a["action"] == "skill.proposal_approve" for a in audit.search_audit())


def test_reject_proposal_closes_without_change(client, monkeypatch):
    closed, applied = [], []
    monkeypatch.setattr(api, "reflection_close_proposal", lambda pid: closed.append(pid))
    monkeypatch.setattr(api, "reflection_apply_proposal", lambda pid: applied.append(pid))
    token, _ = _session_for("admin")
    r = client.post("/admin/skills/proposals/p2/reject", headers=_hdr(token))
    assert r.status_code == 200
    assert closed == ["p2"] and applied == []


def test_list_proposals_uses_reflection(client, monkeypatch):
    monkeypatch.setattr(api, "reflection_list_proposals", lambda: [{"id": "p1", "kind": "create"}])
    token, _ = _session_for("viewer")
    r = client.get("/admin/skills/proposals", headers=_hdr(token))
    assert r.json()[0]["id"] == "p1"
