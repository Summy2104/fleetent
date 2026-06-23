"""Tests for skill_admin_api (the /admin/skills management face).

Engine / reflection / askit seams are monkeypatched so the tests exercise the
management behaviour (gating, reference protection, audit, role guards) rather
than engine semantics. Covers platform.md scenarios 47-57.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.skill_management.skill_admin_api as api
import fleetent.platform.skill_management.skill_admin_store as store
import fleetent.user_store as user_store
from fleetent.db import SQLiteDatabase
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
    # reflection no longer falls back to DATABASE_URL (agent-runtime-db-routing-cleanup):
    # inject the proposals DB the real-reflection tests write to via _insert_proposal.
    from fleetent import reflection

    monkeypatch.setattr(reflection, "_state_db", SQLiteDatabase(path=db_path))
    # neutral engine seams by default; individual tests override.
    monkeypatch.setattr(api, "engine_list_skills", lambda: [])
    monkeypatch.setattr(api, "engine_audit", lambda content: {"verdict": "pass", "rules": []})
    monkeypatch.setattr(api, "engine_reload", lambda: {"ok": True})
    monkeypatch.setattr(api, "engine_set_global_disabled", lambda n, d: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
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


# --- list / edit / source pipeline -------------------------------------------


def test_list_reports_source_and_per_agent_drift_summary(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "engine_list_skills",
        lambda: [
            {"name": "crm-ops", "description": "CRM ops"},
            {"name": "billing", "description": "Billing"},
        ],
    )
    agent = agent_store.create_agent("support", "Prompt.", ["shell"])
    store.set_binding(agent.id, "crm-ops", enabled=True, updated_by="admin")
    store.set_binding(agent.id, "billing", enabled=True, updated_by="admin")
    store.set_source("crm-ops", "managed")
    store.set_drift(agent.id, "crm-ops", drifted=True)
    token, _ = _session_for("viewer")

    rows = client.get("/admin/skills", headers=_hdr(token)).json()
    crm = next(row for row in rows if row["name"] == "crm-ops")
    billing = next(row for row in rows if row["name"] == "billing")

    assert crm["source"] == "managed"
    assert crm["drifted_agents"] == [agent.id]
    assert "drift" not in crm
    assert billing["drifted_agents"] == []


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


def test_edit_does_not_return_immutable_warning_or_per_skill_drift(client, monkeypatch):
    store.set_source("s", "managed", immutable_fields=["name"])
    token, _ = _session_for("admin")
    r = client.put("/admin/skills/s", headers=_hdr(token), json={"content": _VALID})
    assert "immutable_warning" not in r.json()
    assert "drift" not in r.json()


def test_create_and_import_write_source_to_skills_master(client, tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")

    created = client.post(
        "/admin/skills",
        headers=_hdr(token),
        json={
            "name": "created",
            "content": _VALID.replace("name: s", "name: created"),
            "source": "managed",
        },
    )
    assert created.status_code == 200
    assert store.get_source("created")["source"] == "managed"

    files = [("files", ("alpha/SKILL.md", b"---\nname: alpha\ndescription: d\n---\nbody"))]
    imported = client.post(
        "/admin/skills/import/upload",
        headers=_hdr(token),
        files=files,
        data={"source": "managed"},
    )
    assert imported.status_code == 200
    assert store.get_source("alpha")["source"] == "managed"


def test_create_persists_content_to_pool_and_is_readable(client, tmp_path, monkeypatch):
    """Inline create must materialize <skills_dir>/<name>/SKILL.md so the content is
    readable back and the registry rescan indexes it (skill-create-persist-content)."""
    import fleetent.skills.registry as registry

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    # Both the api seam and the registry resolve the pool via FLEETENT_SKILLS_DIR.
    # reload() is pinned to this dir explicitly: the registry's module-level
    # _last_skills_dir is process-shared and may be left pointing elsewhere by a
    # prior test, which a no-arg reload() would otherwise rescan.
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_dir))
    monkeypatch.setattr(api, "engine_reload", lambda: registry.reload(str(skills_dir)))
    monkeypatch.setattr(api, "engine_list_skills", registry.list_skills)
    registry.reload(str(skills_dir))  # start from a clean index over the (empty) pool

    content = "---\nname: persisted\ndescription: a persisted skill\n---\n# persisted\nhello"
    token, _ = _session_for("admin")
    created = client.post(
        "/admin/skills", headers=_hdr(token), json={"name": "persisted", "content": content}
    )
    assert created.status_code == 200
    assert created.json()["published"] is True

    assert (skills_dir / "persisted" / "SKILL.md").read_text(encoding="utf-8") == content
    got = client.get("/admin/skills/persisted/content", headers=_hdr(token))
    assert got.status_code == 200
    assert got.json()["content"] == content
    assert any(s["name"] == "persisted" for s in registry.list_skills())


def test_create_persisted_skill_delivered_in_agent_bundle(client, tmp_path, monkeypatch):
    """A skill created inline must reach a bound agent's node skill-file bundle."""
    import base64

    import fleetent.skills.registry as registry
    from fleetent.platform.agent_lifecycle import materialize

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_dir))
    monkeypatch.setattr(api, "engine_reload", lambda: registry.reload(str(skills_dir)))
    registry.reload(str(skills_dir))

    content = "---\nname: bundled\ndescription: bundled skill\n---\nbody"
    token, _ = _session_for("admin")
    agent = agent_store.create_agent("bundle-bot", "Prompt.", ["shell"])
    assert (
        client.post(
            "/admin/skills", headers=_hdr(token), json={"name": "bundled", "content": content}
        ).status_code
        == 200
    )
    store.set_binding(agent.id, "bundled", enabled=True, updated_by="admin")

    bundles = materialize.skill_bundles_for_agent(agent)
    bundle = next(b for b in bundles if b["name"] == "bundled")
    skill_md = next(f for f in bundle["files"] if f["path"] == "SKILL.md")
    assert base64.b64decode(skill_md["content_b64"]).decode("utf-8") == content


def test_create_rejected_not_persisted(client, tmp_path, monkeypatch):
    """A rejected (quarantined) skill must not be written to the skills pool."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    monkeypatch.setattr(
        api, "engine_audit", lambda content: {"verdict": "rejected", "rules": ["os.system("]}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/skills", headers=_hdr(token), json={"name": "evil", "content": _VALID})
    assert r.status_code == 200
    assert r.json()["published"] is False
    assert not (skills_dir / "evil").exists()


def test_create_unsafe_name_rejected_without_persisting(client, tmp_path, monkeypatch):
    """An unsafe skill name (path traversal) is rejected 422 and nothing is written."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/skills", headers=_hdr(token), json={"name": "../evil", "content": _VALID}
    )
    assert r.status_code == 422
    assert list(skills_dir.iterdir()) == []


def test_provenance_promote_discard_endpoints_removed(client):
    token, _ = _session_for("admin")
    promoted = client.post("/admin/skills/s/provenance/promote", headers=_hdr(token, confirm=True))
    assert promoted.status_code == 404
    assert client.post("/admin/skills/s/provenance/discard", headers=_hdr(token)).status_code == 404


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
    agent = agent_store.create_agent("agent-x", "Prompt.", ["shell"])
    store.set_binding(agent.id, "s", enabled=True, updated_by="admin")
    token, _ = _session_for("admin")
    r = client.delete("/admin/skills/s", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert agent.id in r.json()["detail"]["agents"]
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
    agent_a = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    agent_b = agent_store.create_agent("agent-b", "Prompt.", ["shell"])
    token, _ = _session_for("admin")
    client.put(f"/admin/skills/s/agents/{agent_a.id}", headers=_hdr(token), json={"enabled": True})
    client.put(f"/admin/skills/s/agents/{agent_b.id}", headers=_hdr(token), json={"enabled": False})
    enabling = store.agents_enabling("s")
    assert enabling == [agent_a.id]  # b disabled, a still enabled


# --- force publish ------------------------------------------------------------


def test_force_publish_requires_confirm(client):
    token, _ = _session_for("admin")
    assert client.post("/admin/skills/s/force-publish", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/skills/s/force-publish", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert store.get_state("s")["forced"] == 1


# --- proposal inbox (场景 54/55) ---------------------------------------------


def test_skill_proposal_actions_removed_but_list_and_diff_remain() -> None:
    paths = {getattr(route, "path", None) for route in api.router.routes}
    assert "/admin/skills/proposals" in paths
    assert "/admin/skills/proposals/{proposal_id}/diff" in paths
    assert "/admin/skills/proposals/{proposal_id}/approve" not in paths
    assert "/admin/skills/proposals/{proposal_id}/reject" not in paths


def test_list_proposals_uses_reflection(client, monkeypatch):
    monkeypatch.setattr(api, "reflection_list_proposals", lambda: [{"id": "p1", "kind": "create"}])
    token, _ = _session_for("viewer")
    r = client.get("/admin/skills/proposals", headers=_hdr(token))
    assert r.json()[0]["id"] == "p1"


def _insert_proposal(db_path, pid="pr1", status="pending"):
    import json
    import sqlite3

    now = "2026-06-04T00:00:00+00:00"
    payload_json = json.dumps(
        {
            "name": "demo",
            "description": "demo skill",
            "suggested_draft": "---\nname: demo\ndescription: demo\n---\nbody",
            "suggested_diff": "@@ -1 +1 @@",
            "files": {"SKILL.md": "---\nname: demo\ndescription: demo\n---\nbody"},
        }
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO reflection_proposals
           (id, domain, kind, subject_user_id, target_ref, payload_json, reason,
            evidence_json, risk, actor_user_id, applied_at, created_at, updated_at)
           VALUES (?, 'skill', 'create_skill', NULL, 'demo',
                   ?,
                   'because logs', '["t1"]', 'low', NULL, NULL, ?, ?)""",
        (pid, payload_json, now, now),
    )
    if status != "pending":
        conn.execute(
            """INSERT INTO approval_requests
               (id, subject_type, subject_id, requester_user_id, risk, status,
                approver_user_id, decided_at, reason, routing_key, created_at, expires_at)
               VALUES (?, 'skill_proposal', ?, NULL, 'low', ?, 'reviewer', ?, NULL,
                       'reflection_skill_proposal', ?, NULL)""",
            (pid, pid, status, now, now),
        )
    conn.commit()
    conn.close()


def test_list_proposals_real_reflection(client):
    from fleetent import reflection

    _insert_proposal(reflection._state_db.path)
    token, _ = _session_for("admin")
    rows = client.get("/admin/skills/proposals", headers=_hdr(token)).json()
    assert any(p["id"] == "pr1" and p["target_skill"] == "demo" for p in rows)
    assert rows[0]["risk_level"] == "low"
    assert rows[0]["has_diff"] is True


def test_proposal_diff_real_reflection(client):
    from fleetent import reflection

    _insert_proposal(reflection._state_db.path, pid="pr2")
    token, _ = _session_for("admin")
    r = client.get("/admin/skills/proposals/pr2/diff", headers=_hdr(token)).json()
    assert "@@" in r["diff"]
    assert r["target_skill"] == "demo"


def test_skill_content_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        api, "engine_skill_content", lambda n: "---\nname: x\n---\nbody" if n == "x" else None
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/skills/x/content", headers=_hdr(token))
    assert r.status_code == 200
    assert "body" in r.json()["content"]
    assert client.get("/admin/skills/ghost/content", headers=_hdr(token)).status_code == 404


def test_import_upload_single_folder(client, tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")
    # browser webkitdirectory: filenames are folder-relative (single skill folder "alpha")
    files = [
        ("files", ("alpha/SKILL.md", b"---\nname: alpha\ndescription: d\n---\nbody")),
        ("files", ("alpha/run.sh", b"echo hi")),
    ]
    r = client.post("/admin/skills/import/upload", headers=_hdr(token), files=files)
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["imported"]] == ["alpha"]
    assert (skills_dir / "alpha" / "SKILL.md").exists()
    assert (skills_dir / "alpha" / "run.sh").exists()


def test_import_upload_batch_folder(client, tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")
    # bundle/ has no top SKILL.md -> auto-detected as batch
    files = [
        ("files", ("bundle/one/SKILL.md", b"---\nname: one\ndescription: d\n---\nb")),
        ("files", ("bundle/two/SKILL.md", b"---\nname: two\ndescription: d\n---\nb")),
        ("files", ("bundle/readme.txt", b"not a skill")),
    ]
    r = client.post("/admin/skills/import/upload", headers=_hdr(token), files=files)
    assert {i["name"] for i in r.json()["imported"]} == {"one", "two"}


def test_import_upload_zip(client, tmp_path, monkeypatch):
    import io
    import zipfile

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")
    # a .zip is the reliable fallback when the OS folder picker is blocked
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alpha/SKILL.md", "---\nname: alpha\ndescription: d\n---\nbody")
        zf.writestr("alpha/run.sh", "echo hi")
    files = [("files", ("skills.zip", buf.getvalue(), "application/zip"))]
    r = client.post("/admin/skills/import/upload", headers=_hdr(token), files=files)
    assert r.status_code == 200, r.text
    assert [i["name"] for i in r.json()["imported"]] == ["alpha"]
    assert (skills_dir / "alpha" / "SKILL.md").exists()


def test_import_upload_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    files = [("files", ("a/SKILL.md", b"---\nname: a\ndescription: d\n---\nb"))]
    r = client.post("/admin/skills/import/upload", headers=_hdr(token), files=files)
    assert r.status_code == 403


def test_import_upload_bad_frontmatter_skipped(client, tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(api, "engine_skills_dir", lambda: str(skills_dir))
    token, _ = _session_for("admin")
    files = [
        ("files", ("bundle/good/SKILL.md", b"---\nname: good\ndescription: d\n---\nb")),
        ("files", ("bundle/bad/SKILL.md", b"no frontmatter here")),
    ]
    r = client.post("/admin/skills/import/upload", headers=_hdr(token), files=files)
    body = r.json()
    assert [i["name"] for i in body["imported"]] == ["good"]
    assert body["skipped"][0]["dir"] == "bad"
