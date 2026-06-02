"""Tests for kb_admin_api (/admin/kb). Covers platform.md scenarios 103-108.

Engine seams are monkeypatched so the tests exercise the management behaviour
(uniqueness, binding protection, role guards, audit, seam pass-through).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_kbs_store as kbs_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.kb_admin_api as api
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
    monkeypatch.setattr(api, "kb_engine_list", lambda tenant_id: [])
    monkeypatch.setattr(api, "kb_engine_create", lambda t, k, d: None)
    monkeypatch.setattr(api, "kb_engine_archive", lambda t, k: None)
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


# --- auth / role (场景 108) ---------------------------------------------------


def test_no_auth_401(client):
    assert client.get("/admin/kb").status_code == 401


def test_viewer_can_list(client):
    token, _ = _session_for("viewer")
    assert client.get("/admin/kb", headers=_hdr(token)).status_code == 200


def test_viewer_cannot_create(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/kb", headers=_hdr(token), json={"kb_id": "sales"})
    assert r.status_code == 403


# --- create + uniqueness (场景 103/104) --------------------------------------


def test_create_kb(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/kb", headers=_hdr(token), json={"kb_id": "sales", "description": "x"})
    assert r.status_code == 200
    assert any(a["action"] == "kb_create" for a in audit.search_audit())


def test_create_duplicate_kb_rejected(client, monkeypatch):
    monkeypatch.setattr(api, "kb_engine_list", lambda tenant_id: [{"kb_id": "sales"}])
    token, _ = _session_for("admin")
    r = client.post("/admin/kb", headers=_hdr(token), json={"kb_id": "sales"})
    assert r.status_code == 409


def test_import_document_passes_through(client, monkeypatch):  # 场景 103
    seen = {}
    monkeypatch.setattr(
        api,
        "kb_ingest_text",
        lambda t, k, source, content, fmt: (
            seen.update(t=t, k=k, source=source, fmt=fmt) or {"document_id": "d1", "chunks": 3}
        ),
    )
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/kb/sales/documents",
        headers=_hdr(token),
        json={"source": "paste", "content": "hello", "document_format": "markdown"},
    )
    assert r.status_code == 200
    assert r.json()["chunks"] == 3
    assert seen == {"t": "default", "k": "sales", "source": "paste", "fmt": "markdown"}


def test_import_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/kb/sales/documents", headers=_hdr(token), json={"source": "paste", "content": "hi"}
    )
    assert r.status_code == 403


# --- retrieval playground (场景 105) -----------------------------------------


def test_retrieval_playground(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "kb_search",
        lambda query, tenant_id, kb_ids, mode, limit: [
            {"score": 0.9, "document_id": "d1", "position": 0, "section": "intro"}
        ][:limit],
    )
    token, _ = _session_for("viewer")  # viewer may run read-only
    r = client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "q", "kb_ids": ["sales", "support"], "mode": "hybrid", "top_k": 5},
    )
    assert r.status_code == 200
    assert r.json()["results"][0]["score"] == 0.9
    assert r.json()["kb_ids"] == ["sales", "support"]


def test_retrieval_unknown_mode_422(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "q", "kb_ids": ["sales"], "mode": "bogus"},
    )
    assert r.status_code == 422


# --- archive + binding protection (场景 106) ---------------------------------


def test_archive_blocked_when_bound(client):
    kbs_store.bind("default", "sales", "agent-a")
    token, _ = _session_for("admin")
    r = client.delete("/admin/kb/sales", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert "agent-a" in r.json()["detail"]["agents"]


def test_archive_requires_confirm_when_unbound(client):
    token, _ = _session_for("admin")
    assert client.delete("/admin/kb/sales", headers=_hdr(token)).status_code == 428
    r = client.delete("/admin/kb/sales", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert r.json()["archived"] is True


def test_unbind_then_archive_succeeds(client):
    kbs_store.bind("default", "sales", "agent-a")
    token, _ = _session_for("admin")
    client.delete("/admin/kb/sales/agents/agent-a", headers=_hdr(token))
    r = client.delete("/admin/kb/sales", headers=_hdr(token, confirm=True))
    assert r.status_code == 200


# --- single document delete cascade (场景 107) -------------------------------


def test_delete_document_cascades(client, monkeypatch):
    deleted = []
    monkeypatch.setattr(api, "kb_delete_document", lambda doc_id: deleted.append(doc_id))
    token, _ = _session_for("admin")
    r = client.delete("/admin/kb/sales/documents/d1", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert deleted == ["d1"]
    assert any(a["action"] == "doc_delete" for a in audit.search_audit())


def test_delete_document_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    r = client.delete("/admin/kb/sales/documents/d1", headers=_hdr(token, confirm=True))
    assert r.status_code == 403


# --- binding matrix both directions -------------------------------------------


def test_bind_and_reverse_lookup_consistent(client):
    token, _ = _session_for("admin")
    client.post("/admin/kb/sales/agents", headers=_hdr(token), json={"agent_id": "agent-a"})
    fwd = client.get("/admin/kb/sales/agents", headers=_hdr(token)).json()
    rev = client.get("/admin/kb/by-agent/agent-a", headers=_hdr(token)).json()
    assert fwd["agents"] == ["agent-a"]
    assert rev["kb_ids"] == ["sales"]


def test_eval_entry_read_only_for_viewer(client, monkeypatch):
    monkeypatch.setattr(api, "kb_evaluation", lambda t, k: {"kb_id": k, "metrics": {"hit": 1}})
    token, _ = _session_for("viewer")
    r = client.post("/admin/kb/evaluations", headers=_hdr(token), json={"kb_id": "sales"})
    assert r.status_code == 200
    assert r.json()["metrics"]["hit"] == 1
