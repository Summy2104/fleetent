from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from fleetent.knowledge_base import parsers
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.ingest.config import as_knowledge_base_settings
from fleetent.knowledge_base.ingest.runtime import ingest_parsed
from fleetent.knowledge_base.management.runtime import create_knowledge_base
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


@contextmanager
def _tenant_runtime(home_dir: Path, tenant_id: str):
    from fleetent import knowledge_base as kb_runtime

    scope = TenantRouter(SQLiteTenantBackend(data_dir=home_dir)).tenant_scope(tenant_id)
    previous_db = kb_runtime.runtime._kb_db
    previous_backend = kb_runtime.runtime._kb_vector_backend
    kb_runtime.runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
    kb_runtime.runtime.set_vector_backend(scope.kb_vector_backend)
    try:
        yield scope
    finally:
        kb_runtime.runtime.set_database(previous_db)
        kb_runtime.runtime.set_vector_backend(previous_backend)


def _seed_tenant_kb(home_dir: Path, tenant_id: str, kb_id: str, filename: str, content: str) -> None:
    with _tenant_runtime(home_dir, tenant_id) as scope:
        kb_db = scope.open_kb_db(KB_MIGRATIONS)
        create_knowledge_base(tenant_id, kb_id, f"{tenant_id} KB", database=kb_db)
        asyncio.run(
            ingest_parsed(
                parsers.parse_markdown(filename, content),
                tenant_id=tenant_id,
                kb_id=kb_id,
                source=filename,
                source_url=None,
                settings=as_knowledge_base_settings(
                    default_tenant_id=tenant_id,
                    default_kb_id=kb_id,
                ),
                database=kb_db,
            )
        )


def _headers(tenant_id: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer svc-test",
        "X-Fleetent-Principal": f'{{"user_id":"user-1","tenant_id":"{tenant_id}"}}',
    }


def test_kb_serve_routes_requests_by_principal_tenant(tmp_path: Path, monkeypatch) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_tenant_kb(tmp_path, "tenant-a", "kb-a", "a.md", "# Alpha\nTenant A handbook")
    _seed_tenant_kb(tmp_path, "tenant-b", "kb-b", "b.md", "# Beta\nTenant B playbook")

    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
            multi_tenant_root=True,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        list_a = client.get("/kb", headers=_headers("tenant-a"))
        list_b = client.get("/kb", headers=_headers("tenant-b"))
        search_a = client.post(
            "/search",
            json={
                "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
                "query": "handbook",
                "kb_ids": ["kb-a"],
                "limit": 3,
            },
            headers=_headers("tenant-a"),
        )
        search_b = client.post(
            "/search",
            json={
                "principal": {"user_id": "user-1", "tenant_id": "tenant-b"},
                "query": "playbook",
                "kb_ids": ["kb-b"],
                "limit": 3,
            },
            headers=_headers("tenant-b"),
        )

    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert [row["kb_id"] for row in list_a.json()] == ["kb-a"]
    assert [row["kb_id"] for row in list_b.json()] == ["kb-b"]
    assert search_a.status_code == 200
    assert search_b.status_code == 200
    assert search_a.json()["chunks"][0]["tenant_id"] == "tenant-a"
    assert search_a.json()["chunks"][0]["filename"] == "a.md"
    assert search_b.json()["chunks"][0]["tenant_id"] == "tenant-b"
    assert search_b.json()["chunks"][0]["filename"] == "b.md"


def test_kb_serve_tenant_lock_rejects_other_tenants(tmp_path: Path, monkeypatch) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_tenant_kb(tmp_path, "tenant-a", "kb-a", "a.md", "# Alpha\nTenant A handbook")

    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
            multi_tenant_root=True,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get("/kb", headers=_headers("tenant-b"))

    assert response.status_code == 403
    assert response.json() == {"detail": "tenant mismatch"}
