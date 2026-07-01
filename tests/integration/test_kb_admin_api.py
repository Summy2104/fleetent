"""Tests for kb_admin_api (/admin/kb). Covers platform.md scenarios 103-108.

Engine seams are monkeypatched so the tests exercise the management behaviour
(uniqueness, binding protection, role guards, audit, seam pass-through).
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_api as agent_admin_api
import fleetent.platform.knowledge_base_management.agent_kbs_store as kbs_store
import fleetent.platform.knowledge_base_management.kb_admin_api as api
import fleetent.user_store as user_store
from fleetent import vector_store
from fleetent.knowledge_base import parsers as kb_parsers
from fleetent.knowledge_base.ingest.config import as_knowledge_base_settings
from fleetent.knowledge_base.ingest.runtime import ingest_parsed
from fleetent.observability.traces import TraceEvent
from fleetent.vector_store import SearchResult
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(api, "kb_engine_list", lambda tenant_id: [])
    monkeypatch.setattr(api, "kb_engine_create", lambda t, k, d: None)
    monkeypatch.setattr(api, "kb_engine_archive", lambda t, k: None)
    app = FastAPI()
    app.include_router(agent_admin_api.router)
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

    indexed_chunks: dict[str, dict[str, str]] = {}

    async def embed_text(text: str) -> list[float]:
        return [1.0, 0.0]

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

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", upsert)
    monkeypatch.setattr(vector_store, "search", search)
    monkeypatch.setattr(vector_store, "delete", delete)
    app = FastAPI()
    app.include_router(agent_admin_api.router)
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


def _seed_document(
    tenant_id: str,
    kb_id: str,
    *,
    source: str,
    content: str,
    document_format: str = "markdown",
):
    parser = {
        "markdown": kb_parsers.parse_markdown,
        "text": kb_parsers.parse_text,
        "html": kb_parsers.parse_html,
    }[document_format]
    with api._use_kb_runtime(tenant_id):
        return api.asyncio.run(
            ingest_parsed(
                parser(source, content),
                tenant_id=tenant_id,
                kb_id=kb_id,
                source=source,
                source_url=None,
                settings=as_knowledge_base_settings(
                    default_tenant_id=tenant_id,
                    default_kb_id=kb_id,
                ),
                database=api._knowledge_database(tenant_id),
            )
        )


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

    document = _seed_document(
        "default",
        "support",
        source="support-guide.md",
        content="# Reset Guide\n\nRestart the billing service when ERR42 appears.",
    )

    documents = host_wired_client.get("/admin/kb/support/documents", headers=_hdr(token))
    assert documents.status_code == 200
    assert documents.json() == [
        {
            "document_id": document.id,
            "filename": "support-guide.md",
            "source": "support-guide.md",
            "source_url": None,
            "chunks": documents.json()[0]["chunks"],
            "created_at": documents.json()[0]["created_at"],
        }
    ]

    chunks = host_wired_client.get(
        f"/admin/kb/support/documents/{document.id}/chunks",
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
    assert search.json()["results"][0]["document_id"] == document.id
    assert search.json()["results"][0]["content"] == (
        "Restart the billing service when ERR42 appears."
    )
    assert search.json()["results"][0]["filename"] == "support-guide.md"

    deleted = host_wired_client.delete(
        f"/admin/kb/support/documents/{document.id}",
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


def test_connector_management_endpoints_are_retired(client):
    paths = client.app.openapi()["paths"]

    assert "/admin/kb/connectors" not in paths
    assert "/admin/kb/connectors/{connector_id}" not in paths
    assert "/admin/kb/connectors/{connector_id}/check" not in paths
    assert "/admin/kb/connectors/{connector_id}/status" not in paths
    assert "/admin/kb/connectors/{connector_id}/sync" not in paths


def test_platform_ingest_endpoints_are_retired_but_document_lifecycle_routes_remain(client):
    paths = client.app.openapi()["paths"]

    assert "/admin/kb/{kb_id}/documents" in paths
    assert "get" in paths["/admin/kb/{kb_id}/documents"]
    assert "post" not in paths["/admin/kb/{kb_id}/documents"]
    assert "/admin/kb/{kb_id}/documents/{document_id}/chunks" in paths
    assert "get" in paths["/admin/kb/{kb_id}/documents/{document_id}/chunks"]
    assert "/admin/kb/{kb_id}/documents/{document_id}" in paths
    assert "delete" in paths["/admin/kb/{kb_id}/documents/{document_id}"]
    assert "/admin/kb/{kb_id}/sync" not in paths
    assert "/admin/kb/{kb_id}/extract-entities" not in paths


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
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    kbs_store.bind("default", "sales", agent.id)
    token, _ = _session_for("admin")
    r = client.delete("/admin/kb/sales", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert agent.id in r.json()["detail"]["agents"]


def test_archive_requires_confirm_when_unbound(client):
    token, _ = _session_for("admin")
    assert client.delete("/admin/kb/sales", headers=_hdr(token)).status_code == 428
    r = client.delete("/admin/kb/sales", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert r.json()["archived"] is True


def test_unbind_then_archive_succeeds(client):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    kbs_store.bind("default", "sales", agent.id)
    token, _ = _session_for("admin")
    client.delete(f"/admin/kb/sales/agents/{agent.id}", headers=_hdr(token))
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
    _seed_document(
        "default",
        "support",
        source="support-guide.md",
        content="# Reset Guide\n\nRestart the billing service when ERR42 appears.",
    )

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

    bind = host_wired_client.post(
        "/admin/kb/support/agents",
        headers=_hdr(token),
        json={"agent_id": 1},
    )
    assert bind.status_code == 409

    stale_agent = agent_store.create_agent("agent-stale", "Prompt.", ["shell"])
    kbs_store.bind("default", "support", stale_agent.id)
    retired = host_wired_client.get(f"/admin/kb/by-agent/{stale_agent.id}", headers=_hdr(token))
    assert retired.status_code == 404
    reverse = host_wired_client.get("/admin/agents/agent-stale/kbs", headers=_hdr(token))
    assert reverse.status_code == 200
    assert reverse.json() == {"agent": "agent-stale", "kb_ids": []}


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
    document = _seed_document(
        "default",
        "support",
        source="support-guide.md",
        content="# Reset Guide\n\nRestart the billing service when ERR42 appears.",
    )
    document_id = document.id

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
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    token, _ = _session_for("admin")
    client.post("/admin/kb/sales/agents", headers=_hdr(token), json={"agent_id": agent.id})
    fwd = client.get("/admin/kb/sales/agents", headers=_hdr(token)).json()
    rev = client.get("/admin/agents/agent-a/kbs", headers=_hdr(token)).json()
    assert fwd["agents"] == [agent.id]
    assert rev["agent"] == "agent-a"
    assert rev["kb_ids"] == ["sales"]


def test_eval_entry_read_only_for_viewer(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/kb/evaluations", headers=_hdr(token), json={"kb_id": "sales"})
    assert r.status_code == 200
    body = r.json()
    assert body["kb_id"] == "sales"
    assert body["metrics"]["recall_at_k"] == 1.0
    assert body["metrics"]["mrr"] == 1.0
    assert body["metrics"]["query_count"] >= 1
    assert body["hit_ranking"][0]["rank"] == 1
    assert "wired" not in body


# --- reverse lookup excludes archived KBs (任务 2.3/2.4) ----------------------


def test_by_agent_route_is_retired(client):
    token, _ = _session_for("admin")
    assert client.get("/admin/kb/by-agent/1", headers=_hdr(token)).status_code == 404


def test_agent_reverse_lookup_filters_archived(client, monkeypatch):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    monkeypatch.setattr(
        api,
        "kb_engine_list",
        lambda tenant_id: [{"kb_id": "live"}, {"kb_id": "old", "archived": True}],
    )
    monkeypatch.setattr(
        agent_admin_api,
        "kb_engine_list",
        lambda tenant_id: [{"kb_id": "live"}, {"kb_id": "old", "archived": True}],
        raising=False,
    )
    kbs_store.bind("default", "live", agent.id)
    kbs_store.bind("default", "old", agent.id)
    token, _ = _session_for("admin")
    rev = client.get("/admin/agents/agent-a/kbs", headers=_hdr(token)).json()
    assert rev == {"agent": "agent-a", "kb_ids": ["live"]}


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
    def _event(
        agent_name: str, session_id: str, latency_ms: float, hit_count: int, scores: list[float]
    ):
        return TraceEvent(
            run_id=f"run-{session_id}",
            event_type="kb_retrieval",
            payload={
                "latency_ms": latency_ms,
                "hit_count": hit_count,
                "scores": scores,
                "kb_ids": ["sales"],
            },
            agent_name=agent_name,
            session_id=session_id,
            ts=datetime(2026, 6, 22, 10, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(api.agent_kbs_store, "list_agents_for_kb", lambda tenant_id, kb_id: [7, 8])
    monkeypatch.setattr(
        api.kb_observation_agg.agent_store,
        "get_agent_name_by_id",
        lambda agent_id: {7: "ops-a", 8: "ops-b"}[agent_id],
    )
    monkeypatch.setattr(
        api.kb_observation_agg,
        "query_trace_events",
        lambda query: iter(
            {
                "ops-a": [
                    _event("ops-a", "s1", 10.0, 2, [0.9, 0.6]),
                    _event("ops-a", "s2", 20.0, 0, []),
                ],
                "ops-b": [_event("ops-b", "s3", 40.0, 1, [0.4])],
            }.get(str(query.agent_name), [])
        ),
    )
    token, _ = _session_for("viewer")  # read-only, viewer allowed
    r = client.get("/admin/kb/sales/observation", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["kb_id"] == "sales"
    assert body["query_count"] == 3
    assert body["hit_count"] == 3
    assert body["zero_recall_rate"] == 1 / 3
    assert body["latency_ms"] == {"p50": 20.0, "p95": 40.0}
    assert body["score_distribution"] == {
        "count": 3,
        "min": 0.4,
        "p50": 0.6,
        "p95": 0.9,
        "max": 0.9,
    }
    assert body["sessions"] == ["s1", "s2", "s3"]
    assert "recall_hits" not in body
    assert "recall_at_k" not in body
    assert "mrr" not in body
    assert "citation_rate" not in body
