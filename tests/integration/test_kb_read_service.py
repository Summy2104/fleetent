from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from fleetent.knowledge_base import KnowledgeChunk


@dataclass(frozen=True)
class _FakeScope:
    kb_db: object
    kb_vector_backend: object

    def open_kb_db(self, _migrations: list[tuple[int, str]]) -> object:
        return self.kb_db


def _make_client(monkeypatch) -> tuple[object, TestClient]:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    monkeypatch.setattr(
        serve,
        "_tenant_router",
        lambda: type(
            "_FakeRouter",
            (),
            {
                "tenant_scope": lambda _self, _tenant_id: _FakeScope(
                    kb_db=object(), kb_vector_backend=object()
                )
            },
        )(),
    )
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
        )
    )
    return serve, TestClient(app, raise_server_exceptions=True)


def test_kb_serve_bootstraps_tenant_runtime_once(monkeypatch) -> None:
    from fleetent.knowledge_base import serve

    fake_db = object()
    fake_backend = object()
    captured: dict[str, object] = {}
    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")

    class _FakeRouter:
        def tenant_scope(self, tenant_id: str) -> _FakeScope:
            captured["tenant_id"] = tenant_id
            return _FakeScope(kb_db=fake_db, kb_vector_backend=fake_backend)

    monkeypatch.setattr(serve, "_tenant_router", lambda: _FakeRouter())
    monkeypatch.setattr(
        serve.kb_runtime.runtime,
        "set_database",
        lambda db: captured.setdefault("db", db),
    )
    monkeypatch.setattr(
        serve.kb_runtime.runtime,
        "set_vector_backend",
        lambda backend: captured.setdefault("backend", backend),
    )

    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
        )
    )

    assert app is not None
    assert captured == {
        "tenant_id": "tenant-a",
        "db": fake_db,
        "backend": fake_backend,
    }


def test_search_returns_wire_chunks(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)

    async def fake_search(**_kwargs) -> list[KnowledgeChunk]:
        return [
            KnowledgeChunk(
                id="chunk-1",
                document_id="doc-1",
                tenant_id="tenant-a",
                kb_id="kb-1",
                filename="guide.md",
                content="remote kb result",
                position=2,
                score=0.9,
                source="manual",
                source_url="https://kb.example/doc-1",
                metadata={"section": "deploy"},
            )
        ]

    monkeypatch.setattr(serve.kb_runtime, "search", fake_search)

    response = client.post(
        "/search",
        json={
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "deploy",
            "kb_ids": ["kb-1"],
            "limit": 3,
        },
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "chunks": [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "tenant_id": "tenant-a",
                "kb_id": "kb-1",
                "filename": "guide.md",
                "content": "remote kb result",
                "position": 2,
                "score": 0.9,
                "source": "manual",
                "source_url": "https://kb.example/doc-1",
                "metadata": {"section": "deploy"},
            }
        ]
    }


def test_status_returns_connector_and_job_state(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)

    monkeypatch.setattr(
        serve.kb_runtime.operations,
        "list_connector_statuses",
        lambda tenant_id, kb_id=None: [
            serve.kb_runtime.ConnectorStatus(
                connector_id="drive-a",
                connector_type="google_drive",
                tenant_id=tenant_id,
                kb_id="kb-a",
                last_status="sync_succeeded",
                last_started_at=datetime(2026, 6, 30, 10, 0, tzinfo=UTC),
                last_finished_at=datetime(2026, 6, 30, 10, 5, tzinfo=UTC),
                last_summary={"ingested": 3},
                last_error=None,
            )
        ],
    )
    monkeypatch.setattr(
        serve.kb_ingest_jobs,
        "list_jobs",
        lambda tenant_id, kb_id=None, database_url=None: [
            {
                "id": "job-1",
                "job_type": "connector_sync",
                "tenant_id": tenant_id,
                "kb_id": "kb-a",
                "status": "done",
                "attempts": 0,
                "max_attempts": 3,
                "last_error": None,
                "created_at": "2026-06-30T10:00:00+00:00",
                "updated_at": "2026-06-30T10:05:00+00:00",
                "claimed_at": "2026-06-30T10:00:10+00:00",
                "finished_at": "2026-06-30T10:05:00+00:00",
                "result": {"status": "sync_succeeded", "summary": {"ingested": 3}},
            }
        ],
    )

    response = client.get(
        "/status",
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant-a",
        "connectors": [
            {
                "connector_id": "drive-a",
                "connector_type": "google_drive",
                "tenant_id": "tenant-a",
                "kb_id": "kb-a",
                "last_status": "sync_succeeded",
                "last_started_at": "2026-06-30T10:00:00+00:00",
                "last_finished_at": "2026-06-30T10:05:00+00:00",
                "last_summary": {"ingested": 3},
                "last_error": None,
            }
        ],
        "jobs": [
            {
                "id": "job-1",
                "job_type": "connector_sync",
                "tenant_id": "tenant-a",
                "kb_id": "kb-a",
                "status": "done",
                "attempts": 0,
                "max_attempts": 3,
                "last_error": None,
                "created_at": "2026-06-30T10:00:00+00:00",
                "updated_at": "2026-06-30T10:05:00+00:00",
                "claimed_at": "2026-06-30T10:00:10+00:00",
                "finished_at": "2026-06-30T10:05:00+00:00",
                "result": {"status": "sync_succeeded", "summary": {"ingested": 3}},
            }
        ],
    }


def test_search_request_defaults_keep_backward_compatible_behavior(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)
    request = serve.SearchRequest.model_validate(
        {
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "deploy",
            "kb_ids": ["kb-1", "kb-2"],
            "limit": 5,
        }
    )
    captured: dict[str, object] = {}

    async def fake_search(**kwargs) -> list[KnowledgeChunk]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(serve.kb_runtime, "search", fake_search)

    response = client.post(
        "/search",
        json={
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "deploy",
            "kb_ids": ["kb-1", "kb-2"],
            "limit": 5,
        },
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
        },
    )

    assert request.mode is None
    assert request.rerank is False
    assert request.use_planner is False
    assert response.status_code == 200
    assert captured == {
        "query": "deploy",
        "tenant_id": "tenant-a",
        "kb_ids": ["kb-1", "kb-2"],
        "limit": 5,
        "mode": "hybrid",
        "rerank": False,
    }


def test_search_passes_explicit_mode_and_rerank_to_runtime(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)
    captured: dict[str, object] = {}

    async def fake_search(**kwargs) -> list[KnowledgeChunk]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(serve.kb_runtime, "search", fake_search)

    response = client.post(
        "/search",
        json={
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "deploy",
            "kb_ids": ["kb-1", "kb-2"],
            "limit": 5,
            "mode": "hybrid",
            "rerank": True,
        },
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
        },
    )

    assert response.status_code == 200
    assert captured == {
        "query": "deploy",
        "tenant_id": "tenant-a",
        "kb_ids": ["kb-1", "kb-2"],
        "limit": 5,
        "mode": "hybrid",
        "rerank": True,
    }


def test_search_uses_planner_when_requested(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)
    captured: dict[str, object] = {}
    planned_chunk = KnowledgeChunk(
        id="planned-1",
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="kb-1",
        filename="graph.md",
        content="planned result",
        position=1,
        score=0.95,
        source="manual",
        source_url=None,
        metadata={},
    )

    def fake_plan(query: str, options) -> object:
        captured["query"] = query
        captured["options"] = options
        return "plan-token"

    async def fake_execute(plan) -> list[KnowledgeChunk]:
        captured["plan"] = plan
        return [planned_chunk]

    async def fail_search(**_kwargs) -> list[KnowledgeChunk]:
        raise AssertionError("kb_runtime.search should not be called when use_planner=true")

    monkeypatch.setattr(serve.kb_runtime, "plan_knowledge_search", fake_plan)
    monkeypatch.setattr(serve.kb_runtime, "execute_knowledge_search_plan", fake_execute)
    monkeypatch.setattr(serve.kb_runtime, "search", fail_search)

    response = client.post(
        "/search",
        json={
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "Which service depends on Billing API?",
            "kb_ids": ["kb-1"],
            "limit": 4,
            "mode": "hybrid",
            "rerank": True,
            "use_planner": True,
        },
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "chunks": [
            {
                "id": "planned-1",
                "document_id": "doc-1",
                "tenant_id": "tenant-a",
                "kb_id": "kb-1",
                "filename": "graph.md",
                "content": "planned result",
                "position": 1,
                "score": 0.95,
                "source": "manual",
                "source_url": None,
                "metadata": {},
            }
        ]
    }
    assert captured["query"] == "Which service depends on Billing API?"
    options = captured["options"]
    assert options.tenant_id == "tenant-a"
    assert options.kb_ids == ["kb-1"]
    assert options.limit == 4
    assert options.rerank is True
    assert captured["plan"] == "plan-token"


def test_search_rejects_rerank_with_non_hybrid_mode_before_planner(monkeypatch) -> None:
    serve, client = _make_client(monkeypatch)

    async def fail_search(**_kwargs) -> list[KnowledgeChunk]:
        raise AssertionError("search should not run for invalid rerank/mode combinations")

    async def fail_execute(_plan) -> list[KnowledgeChunk]:
        raise AssertionError("planner execute should not run for invalid rerank/mode combinations")

    monkeypatch.setattr(serve.kb_runtime, "search", fail_search)
    monkeypatch.setattr(
        serve.kb_runtime,
        "execute_knowledge_search_plan",
        fail_execute,
    )

    with pytest.raises(ValueError, match="rerank only supports hybrid knowledge search mode"):
        client.post(
            "/search",
            json={
                "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
                "query": "deploy",
                "kb_ids": ["kb-1"],
                "limit": 3,
                "mode": "vector",
                "rerank": True,
                "use_planner": True,
            },
            headers={
                "Authorization": "Bearer svc-test",
                "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
            },
        )


def test_search_rejects_missing_or_malformed_auth(monkeypatch) -> None:
    _serve, client = _make_client(monkeypatch)
    payload = {
        "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
        "query": "deploy",
        "kb_ids": ["kb-1"],
        "limit": 3,
    }

    missing_auth = client.post(
        "/search",
        json=payload,
        headers={"X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}'},
    )
    malformed_principal = client.post(
        "/search",
        json=payload,
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": "not-json",
        },
    )

    assert missing_auth.status_code == 401
    assert malformed_principal.status_code == 401


def test_search_rejects_cross_tenant_principal(monkeypatch) -> None:
    _serve, client = _make_client(monkeypatch)

    response = client.post(
        "/search",
        json={
            "principal": {"user_id": "user-1", "tenant_id": "tenant-b"},
            "query": "deploy",
            "kb_ids": ["kb-1"],
            "limit": 3,
        },
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-b"}',
        },
    )

    assert response.status_code == 403


def test_status_rejects_cross_tenant_principal(monkeypatch) -> None:
    _serve, client = _make_client(monkeypatch)

    response = client.get(
        "/status",
        headers={
            "Authorization": "Bearer svc-test",
            "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-b"}',
        },
    )

    assert response.status_code == 403


def test_kb_serve_with_queue_config_does_not_start_sweep_task(monkeypatch, tmp_path) -> None:
    from fleetent.knowledge_base import serve

    path = tmp_path / "service-key.txt"
    path.write_text("svc-test", encoding="utf-8")
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref=f"file://{path}",
            queue_database_url="sqlite:////tmp/kb-queue.db",
        )
    )
    monkeypatch.delenv("FLEETENT_KB_SERVICE_CONFIG", raising=False)

    with TestClient(app, raise_server_exceptions=True):
        pass
