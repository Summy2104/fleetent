"""Tests for kb_admin_api (/admin/kb). Covers platform.md scenarios 103-108.

Engine seams are monkeypatched so the tests exercise the management behaviour
(uniqueness, binding protection, role guards, audit, seam pass-through).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.knowledge_base_management.agent_kbs_store as kbs_store
import fleetent.platform.knowledge_base_management.kb_admin_api as api
import fleetent.user_store as user_store
from fleetent.intelligence import vector_store
from fleetent.intelligence.vector_store import SearchResult
from tests.integration._migration_template import apply_migrations


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


@pytest.fixture
def host_wired_client(tmp_path, monkeypatch):
    db_path = tmp_path / "fleetent.db"
    apply_migrations(db_path)
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KNOWLEDGE_BASE__CHUNK_SIZE", "200")
    monkeypatch.setenv("KNOWLEDGE_BASE__CHUNK_OVERLAP", "0")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)

    indexed_chunks: dict[str, dict[str, str]] = {}

    async def upsert(chunk_id: str, content: str, namespace: str) -> None:
        indexed_chunks[chunk_id] = {"content": content, "namespace": namespace}

    async def search(query: str, namespace: str, limit: int) -> list[SearchResult]:
        return [
            SearchResult(id=chunk_id, score=0.91)
            for chunk_id, chunk in indexed_chunks.items()
            if chunk["namespace"] == namespace and query.lower() in chunk["content"].lower()
        ][:limit]

    async def delete(chunk_id: str, namespace: str) -> None:
        if indexed_chunks.get(chunk_id, {}).get("namespace") == namespace:
            indexed_chunks.pop(chunk_id, None)

    monkeypatch.setattr(vector_store, "upsert", upsert)
    monkeypatch.setattr(vector_store, "search", search)
    monkeypatch.setattr(vector_store, "delete", delete)
    user_store._init_db()
    audit._init_db()
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


def test_default_admin_kb_route_uses_real_host_knowledge_base(host_wired_client):
    token, _ = _session_for("admin")

    created = host_wired_client.post(
        "/admin/kb",
        headers=_hdr(token),
        json={"kb_id": "support", "description": "Support handbook"},
    )
    assert created.status_code == 200

    listed = host_wired_client.get("/admin/kb", headers=_hdr(token))
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "kb_id": "support",
            "tenant_id": "default",
            "description": "Support handbook",
            "doc_count": 0,
            "chunk_count": 0,
            "last_import": None,
            "archived": False,
            "bound_agents": [],
        }
    ]

    edited = host_wired_client.patch(
        "/admin/kb/support",
        headers=_hdr(token),
        json={"description": "Support runbook"},
    )
    assert edited.status_code == 200

    after_edit = host_wired_client.get("/admin/kb", headers=_hdr(token))
    assert after_edit.status_code == 200
    assert after_edit.json()[0]["description"] == "Support runbook"

    imported = host_wired_client.post(
        "/admin/kb/support/documents",
        headers=_hdr(token),
        json={
            "source": "support-guide.md",
            "document_format": "markdown",
            "content": "# Reset Guide\n\nRestart the billing service when ERR42 appears.",
        },
    )
    assert imported.status_code == 200
    import_body = imported.json()
    assert import_body["document_id"]
    assert import_body["chunks"] > 0
    assert import_body["wired"] is True
    assert import_body["filename"] == "support-guide.md"
    assert import_body["source"] == "support-guide.md"

    documents = host_wired_client.get("/admin/kb/support/documents", headers=_hdr(token))
    assert documents.status_code == 200
    assert documents.json() == [
        {
            "document_id": import_body["document_id"],
            "filename": "support-guide.md",
            "source": "support-guide.md",
            "source_url": None,
            "chunks": import_body["chunks"],
            "created_at": documents.json()[0]["created_at"],
        }
    ]

    chunks = host_wired_client.get(
        f"/admin/kb/support/documents/{import_body['document_id']}/chunks",
        headers=_hdr(token),
    )
    assert chunks.status_code == 200
    assert chunks.json()[0]["content"] == "Restart the billing service when ERR42 appears."
    assert chunks.json()[0]["section"] == "Reset Guide"
    assert chunks.json()[0]["section_path"] == "Reset Guide"

    search = host_wired_client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "ERR42", "kb_ids": ["support"], "mode": "hybrid", "top_k": 5},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["document_id"] == import_body["document_id"]
    assert search.json()["results"][0]["content"] == (
        "Restart the billing service when ERR42 appears."
    )
    assert search.json()["results"][0]["filename"] == "support-guide.md"

    deleted = host_wired_client.delete(
        f"/admin/kb/support/documents/{import_body['document_id']}",
        headers=_hdr(token, confirm=True),
    )
    assert deleted.status_code == 200

    after_delete = host_wired_client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "ERR42", "kb_ids": ["support"], "mode": "hybrid", "top_k": 5},
    )
    assert after_delete.status_code == 200
    assert after_delete.json()["results"] == []


def test_host_wired_import_rejects_missing_kb(host_wired_client):
    token, _ = _session_for("admin")

    imported = host_wired_client.post(
        "/admin/kb/missing/documents",
        headers=_hdr(token),
        json={
            "source": "missing.md",
            "document_format": "markdown",
            "content": "# Missing\n\nThis should not create a KB implicitly.",
        },
    )

    assert imported.status_code == 404
    listed = host_wired_client.get("/admin/kb", headers=_hdr(token))
    assert listed.status_code == 200
    assert listed.json() == []


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


def test_retrieval_empty_kb_ids_422(client, monkeypatch):
    def fail_search(query, tenant_id, kb_ids, mode, limit):
        raise AssertionError("empty kb_ids must be rejected before search")

    monkeypatch.setattr(api, "kb_search", fail_search)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "q", "kb_ids": [], "mode": "hybrid"},
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


def test_host_wired_archive_updates_visibility_search_and_binding(host_wired_client):
    token, _ = _session_for("admin")
    created = host_wired_client.post(
        "/admin/kb",
        headers=_hdr(token),
        json={"kb_id": "support", "description": "Support handbook"},
    )
    assert created.status_code == 200
    imported = host_wired_client.post(
        "/admin/kb/support/documents",
        headers=_hdr(token),
        json={
            "source": "support-guide.md",
            "document_format": "markdown",
            "content": "# Reset Guide\n\nRestart the billing service when ERR42 appears.",
        },
    )
    assert imported.status_code == 200

    archived = host_wired_client.delete(
        "/admin/kb/support",
        headers=_hdr(token, confirm=True),
    )
    assert archived.status_code == 200
    assert archived.json() == {"kb_id": "support", "archived": True}

    listed = host_wired_client.get("/admin/kb", headers=_hdr(token))
    assert listed.status_code == 200
    assert listed.json()[0]["archived"] is True

    search = host_wired_client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "ERR42", "kb_ids": ["support"], "mode": "hybrid", "top_k": 5},
    )
    assert search.status_code == 200
    assert search.json()["results"] == []

    import_after_archive = host_wired_client.post(
        "/admin/kb/support/documents",
        headers=_hdr(token),
        json={
            "source": "archived.md",
            "document_format": "markdown",
            "content": "# Archived\n\nThis should not ingest.",
        },
    )
    assert import_after_archive.status_code == 404

    bind = host_wired_client.post(
        "/admin/kb/support/agents",
        headers=_hdr(token),
        json={"agent_id": "agent-a"},
    )
    assert bind.status_code == 409

    kbs_store.bind("default", "support", "agent-stale")
    reverse = host_wired_client.get("/admin/kb/by-agent/agent-stale", headers=_hdr(token))
    assert reverse.status_code == 200
    assert reverse.json()["kb_ids"] == []


# --- single document delete cascade (场景 107) -------------------------------


def test_delete_document_cascades(client, monkeypatch):
    deleted = []
    monkeypatch.setattr(
        api,
        "kb_delete_document",
        lambda tenant_id, kb_id, doc_id: deleted.append((tenant_id, kb_id, doc_id)),
    )
    token, _ = _session_for("admin")
    r = client.delete("/admin/kb/sales/documents/d1", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert deleted == [("default", "sales", "d1")]
    assert any(a["action"] == "doc_delete" for a in audit.search_audit())


def test_host_wired_delete_document_rejects_wrong_kb_and_preserves_document(host_wired_client):
    token, _ = _session_for("admin")
    for kb_id in ("support", "sales"):
        created = host_wired_client.post(
            "/admin/kb",
            headers=_hdr(token),
            json={"kb_id": kb_id, "description": ""},
        )
        assert created.status_code == 200
    imported = host_wired_client.post(
        "/admin/kb/support/documents",
        headers=_hdr(token),
        json={
            "source": "support-guide.md",
            "document_format": "markdown",
            "content": "# Reset Guide\n\nRestart the billing service when ERR42 appears.",
        },
    )
    assert imported.status_code == 200
    document_id = imported.json()["document_id"]

    wrong_kb_delete = host_wired_client.delete(
        f"/admin/kb/sales/documents/{document_id}",
        headers=_hdr(token, confirm=True),
    )
    assert wrong_kb_delete.status_code == 404

    documents = host_wired_client.get("/admin/kb/support/documents", headers=_hdr(token))
    assert documents.status_code == 200
    assert [doc["document_id"] for doc in documents.json()] == [document_id]

    search = host_wired_client.post(
        "/admin/kb/search",
        headers=_hdr(token),
        json={"query": "ERR42", "kb_ids": ["support"], "mode": "hybrid", "top_k": 5},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["document_id"] == document_id


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


# --- reverse lookup excludes archived KBs (任务 2.3/2.4) ----------------------


def test_kbs_for_agent_filters_archived(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "kb_engine_list",
        lambda tenant_id: [{"kb_id": "live"}, {"kb_id": "old", "archived": True}],
    )
    kbs_store.bind("default", "live", "agent-a")
    kbs_store.bind("default", "old", "agent-a")
    token, _ = _session_for("admin")
    rev = client.get("/admin/kb/by-agent/agent-a", headers=_hdr(token)).json()
    assert rev["kb_ids"] == ["live"]  # archived "old" filtered out


# --- local directory sync summary (任务 4.3) ---------------------------------


def test_sync_directory_returns_summary(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        api,
        "kb_sync_directory",
        lambda t, k, path: (
            seen.update(t=t, k=k, path=path)
            or {"scanned": 10, "ingested": 7, "skipped": 2, "failed": 1}
        ),
    )
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/kb/sales/sync",
        headers=_hdr(token, confirm=True),
        json={"path": "/data/docs"},
    )
    assert r.status_code == 200
    assert r.json() == {"scanned": 10, "ingested": 7, "skipped": 2, "failed": 1}
    assert seen == {"t": "default", "k": "sales", "path": "/data/docs"}


def test_host_wired_sync_directory_uses_real_local_sync(host_wired_client, tmp_path):
    fixture_dir = tmp_path / "kb-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "runbook.txt").write_text("Restart billing service for ERR42.", encoding="utf-8")
    token, _ = _session_for("admin")
    created = host_wired_client.post(
        "/admin/kb",
        headers=_hdr(token),
        json={"kb_id": "support", "description": "Support handbook"},
    )
    assert created.status_code == 200

    synced = host_wired_client.post(
        "/admin/kb/support/sync",
        headers=_hdr(token, confirm=True),
        json={"path": str(fixture_dir)},
    )

    assert synced.status_code == 200
    assert synced.json()["wired"] is True
    assert synced.json()["scanned"] == 1
    assert synced.json()["ingested"] == 1
    assert synced.json()["failed"] == 0
    documents = host_wired_client.get("/admin/kb/support/documents", headers=_hdr(token))
    assert documents.status_code == 200
    assert documents.json()[0]["filename"] == "runbook.txt"


def test_sync_directory_requires_confirm(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/kb/sales/sync", headers=_hdr(token), json={"path": "/data/docs"})
    assert r.status_code == 428  # full resync is high-risk


# --- document list + chunk preview (任务 5.1) --------------------------------


def test_list_documents_and_chunk_preview(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "kb_list_documents",
        lambda t, k: [
            {
                "document_id": "d1",
                "filename": "a.md",
                "source": "paste",
                "chunks": 3,
                "created_at": "t0",
            }
        ],
    )
    monkeypatch.setattr(
        api,
        "kb_chunk_preview",
        lambda t, k, doc: [{"chunk_id": "c1", "content": "hello", "section": "intro"}],
    )
    token, _ = _session_for("viewer")  # viewer may read
    docs = client.get("/admin/kb/sales/documents", headers=_hdr(token)).json()
    assert docs[0]["filename"] == "a.md" and docs[0]["chunks"] == 3
    chunks = client.get("/admin/kb/sales/documents/d1/chunks", headers=_hdr(token)).json()
    assert chunks[0]["content"] == "hello" and chunks[0]["section"] == "intro"


# --- per-KB observation (任务 9.1) -------------------------------------------


def test_observation_read_only_aggregation(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "kb_observation",
        lambda t, k: {
            "kb_id": k,
            "recall_hits": 42,
            "zero_recall_docs": ["d9"],
            "sessions": ["s1", "s2"],
        },
    )
    token, _ = _session_for("viewer")  # read-only, viewer allowed
    r = client.get("/admin/kb/sales/observation", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["recall_hits"] == 42
    assert body["zero_recall_docs"] == ["d9"]
    assert body["sessions"] == ["s1", "s2"]
