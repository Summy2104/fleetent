from __future__ import annotations

from dataclasses import dataclass

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


def test_search_passes_explicit_mode_and_request_scope(monkeypatch) -> None:
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
        "rerank": False,
    }


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
