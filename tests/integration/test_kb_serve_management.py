from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _auth_headers(
    *,
    token: str = "svc-test",
    principal: str = '{"user_id":"user-1","tenant_id":"tenant-a"}',
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Fleetent-Principal": principal,
    }


def _seed_document(data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from fleetent import vector_store
    from fleetent.knowledge_base import parsers as kb_parsers
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.ingest.config import as_knowledge_base_settings
    from fleetent.knowledge_base.ingest.runtime import ingest_parsed
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.serve import _tenant_router

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    async def upsert(chunk_id: str, content: str, namespace: str) -> None:
        del chunk_id, content, namespace

    async def delete(chunk_id: str, namespace: str) -> None:
        del chunk_id, namespace

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", upsert)
    monkeypatch.setattr(vector_store, "delete", delete)

    kb_db = _tenant_router(data_dir).tenant_scope("tenant-a").open_kb_db(KB_MIGRATIONS)
    create_knowledge_base("tenant-a", "support", "Support handbook", database=kb_db)
    document = asyncio.run(
        ingest_parsed(
            kb_parsers.parse_markdown(
                "support-guide.md",
                "# Reset Guide\n\nRestart the billing service when ERR42 appears.",
            ),
            tenant_id="tenant-a",
            kb_id="support",
            source="support-guide.md",
            source_url=None,
            settings=as_knowledge_base_settings(
                default_tenant_id="tenant-a", default_kb_id="support"
            ),
            database=kb_db,
        )
    )
    return kb_db, document


def test_read_endpoints_list_kbs_documents_and_chunks(tmp_path: Path, monkeypatch) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _kb_db, document = _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        kbs = client.get("/kb", headers=_auth_headers())
        assert kbs.status_code == 200
        assert kbs.json() == [
            {
                "tenant_id": "tenant-a",
                "kb_id": "support",
                "description": "Support handbook",
                "doc_count": 1,
                "chunk_count": 1,
                "last_import": kbs.json()[0]["last_import"],
                "archived": False,
            }
        ]

        documents = client.get("/kb/support/documents", headers=_auth_headers())
        assert documents.status_code == 200
        assert documents.json() == [
            {
                "document_id": document.id,
                "filename": "support-guide.md",
                "source": "support-guide.md",
                "source_url": None,
                "chunks": 1,
                "created_at": documents.json()[0]["created_at"],
            }
        ]

        chunks = client.get(
            f"/kb/support/documents/{document.id}/chunks",
            headers=_auth_headers(),
        )
        assert chunks.status_code == 200
        assert chunks.json() == [
            {
                "chunk_id": f"{document.id}:chunk:0",
                "document_id": document.id,
                "kb_id": "support",
                "filename": "support-guide.md",
                "content": "Restart the billing service when ERR42 appears.",
                "position": 0,
                "score": 0.0,
                "source": "support-guide.md",
                "source_url": None,
                "section": "Reset Guide",
                "section_path": "Reset Guide",
            }
        ]


def test_read_endpoints_require_auth_and_reject_cross_tenant(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        assert client.get("/kb").status_code == 401
        assert (
            client.get(
                "/kb",
                headers=_auth_headers(
                    principal='{"user_id":"user-1","tenant_id":"tenant-b"}',
                ),
            ).status_code
            == 403
        )


def test_write_endpoints_create_update_archive_and_delete_document(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _kb_db, document = _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        created = client.post(
            "/kb",
            headers=_auth_headers(),
            json={"kb_id": "sales", "description": "Sales handbook"},
        )
        assert created.status_code == 200
        assert created.json() == {
            "kb_id": "sales",
            "tenant_id": "tenant-a",
            "description": "Sales handbook",
            "extraction_enabled": False,
        }

        created_again = client.post(
            "/kb",
            headers=_auth_headers(),
            json={"kb_id": "sales", "description": "Sales handbook"},
        )
        assert created_again.status_code == 200
        assert created_again.json() == created.json()

        patched = client.patch(
            "/kb/sales",
            headers=_auth_headers(),
            json={"description": "Updated sales handbook", "extraction_enabled": True},
        )
        assert patched.status_code == 200
        assert patched.json() == {
            "kb_id": "sales",
            "description": "Updated sales handbook",
            "extraction_enabled": True,
        }

        listed = client.get("/kb", headers=_auth_headers())
        assert listed.status_code == 200
        assert listed.json() == [
            {
                "tenant_id": "tenant-a",
                "kb_id": "sales",
                "description": "Updated sales handbook",
                "doc_count": 0,
                "chunk_count": 0,
                "last_import": None,
                "archived": False,
            },
            {
                "tenant_id": "tenant-a",
                "kb_id": "support",
                "description": "Support handbook",
                "doc_count": 1,
                "chunk_count": 1,
                "last_import": listed.json()[1]["last_import"],
                "archived": False,
            },
        ]

        deleted = client.delete(
            f"/kb/support/documents/{document.id}",
            headers=_auth_headers(),
        )
        assert deleted.status_code == 200
        assert deleted.json() == {
            "kb_id": "support",
            "document_id": document.id,
            "deleted": True,
        }
        assert client.get("/kb/support/documents", headers=_auth_headers()).json() == []

        archived = client.delete("/kb/sales", headers=_auth_headers())
        assert archived.status_code == 200
        assert archived.json() == {"kb_id": "sales", "archived": True}
        listed_after_archive = client.get("/kb", headers=_auth_headers())
        assert listed_after_archive.status_code == 200
        assert listed_after_archive.json()[0]["archived"] is True


def test_write_endpoints_require_auth_and_reject_cross_tenant(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        assert client.post("/kb", json={"kb_id": "sales"}).status_code == 401
        assert (
            client.post(
                "/kb",
                headers=_auth_headers(
                    principal='{"user_id":"user-1","tenant_id":"tenant-b"}',
                ),
                json={"kb_id": "sales"},
            ).status_code
            == 403
        )


def test_evaluation_endpoint_runs_deterministic_fixture_suite(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/evaluations",
            headers=_auth_headers(),
            json={"kb_id": "support"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["kb_id"] == "support"
        assert set(body["metrics"]) == {
            "recall_at_k",
            "mrr",
            "query_count",
            "hit_count",
            "hit_rate",
            "average_hit_rank",
        }
        assert 0.0 <= body["metrics"]["recall_at_k"] <= 1.0
        assert 0.0 <= body["metrics"]["mrr"] <= 1.0
        assert body["metrics"]["query_count"] >= 1
        assert body["metrics"]["hit_count"] >= 1
        assert 0.0 <= body["metrics"]["hit_rate"] <= 1.0
        assert body["hit_ranking"]
        assert body["hit_ranking"][0]["rank"] >= 1
        assert body["fixtures"]
        assert body["fixtures"][0]["queries"]


def test_evaluation_endpoint_requires_auth_and_rejects_cross_tenant(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import serve

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")
    _seed_document(tmp_path, monkeypatch)
    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path,
        )
    )

    with TestClient(app, raise_server_exceptions=True) as client:
        assert client.post("/evaluations", json={"kb_id": "support"}).status_code == 401
        assert (
            client.post(
                "/evaluations",
                headers=_auth_headers(
                    principal='{"user_id":"user-1","tenant_id":"tenant-b"}',
                ),
                json={"kb_id": "support"},
            ).status_code
            == 403
        )
