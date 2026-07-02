from __future__ import annotations

import httpx

from fleetent.config import Settings
from fleetent.platform.knowledge_base_management.kb_serve_client import (
    KBServeClient,
    KBServeSettings,
)


def test_settings_load_kb_serve_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", "svc-test")
    monkeypatch.setenv("KB_SERVE__URL", "http://kb-serve.test")
    monkeypatch.setenv("KB_SERVE__SERVICE_KEY_REF", "env:FLEETENT_PLATFORM_KB_SERVICE_KEY")
    settings = Settings()

    assert settings.kb_serve == KBServeSettings(
        url="http://kb-serve.test",
        service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
    )


def test_search_sends_shared_key_and_principal_headers(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", "svc-test")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == httpx.URL("http://kb-serve.test/search")
        assert request.headers["Authorization"] == "Bearer svc-test"
        assert request.headers["X-Fleetent-Principal"] == (
            '{"user_id":"platform","tenant_id":"tenant-a"}'
        )
        assert request.content == (
            b'{"principal":{"user_id":"platform","tenant_id":"tenant-a"},'
            b'"query":"ERR42","kb_ids":["support"],"limit":7,"mode":"hybrid",'
            b'"rerank":true,"use_planner":true}'
        )
        return httpx.Response(
            200,
            json={
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "tenant_id": "tenant-a",
                        "kb_id": "support",
                        "filename": "support-guide.md",
                        "content": "Restart billing service.",
                        "position": 0,
                        "score": 0.9,
                        "source": "support-guide.md",
                        "source_url": None,
                        "section": "Reset Guide",
                        "section_path": "Reset Guide",
                    }
                ]
            },
        )

    client = KBServeClient(
        KBServeSettings(
            url="http://kb-serve.test",
            service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert client.search(
        tenant_id="tenant-a",
        query="ERR42",
        kb_ids=["support"],
        limit=7,
        mode="hybrid",
        rerank=True,
        use_planner=True,
    ) == {
        "chunks": [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "tenant_id": "tenant-a",
                "kb_id": "support",
                "filename": "support-guide.md",
                "content": "Restart billing service.",
                "position": 0,
                "score": 0.9,
                "source": "support-guide.md",
                "source_url": None,
                "section": "Reset Guide",
                "section_path": "Reset Guide",
            }
        ]
    }
    assert len(requests) == 1


def test_client_covers_management_document_and_evaluation_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", "svc-test")
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        payloads = {
            ("GET", "/kb"): [{"kb_id": "support", "description": "Support"}],
            ("POST", "/kb"): {"kb_id": "support", "description": "Support"},
            ("PATCH", "/kb/support"): {"kb_id": "support", "description": "Updated"},
            ("DELETE", "/kb/support"): {"kb_id": "support", "archived": True},
            ("GET", "/kb/support/documents"): [{"document_id": "doc-1"}],
            ("GET", "/kb/support/documents/doc-1/chunks"): [{"id": "chunk-1"}],
            ("DELETE", "/kb/support/documents/doc-1"): {"deleted": True},
            ("POST", "/evaluations"): {"kb_id": "support", "metrics": {"mrr": 1.0}},
        }
        return httpx.Response(200, json=payloads[(request.method, request.url.path)])

    client = KBServeClient(
        KBServeSettings(
            url="http://kb-serve.test",
            service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert client.list_knowledge_bases("tenant-a") == [
        {"kb_id": "support", "description": "Support"}
    ]
    assert client.create_knowledge_base("tenant-a", "support", "Support") == {
        "kb_id": "support",
        "description": "Support",
    }
    assert client.update_knowledge_base("tenant-a", "support", description="Updated") == {
        "kb_id": "support",
        "description": "Updated",
    }
    assert client.archive_knowledge_base("tenant-a", "support") == {
        "kb_id": "support",
        "archived": True,
    }
    assert client.list_documents("tenant-a", "support") == [{"document_id": "doc-1"}]
    assert client.preview_document_chunks("tenant-a", "support", "doc-1") == [{"id": "chunk-1"}]
    assert client.delete_document("tenant-a", "support", "doc-1") == {"deleted": True}
    assert client.run_evaluation("tenant-a", "support") == {
        "kb_id": "support",
        "metrics": {"mrr": 1.0},
    }

    assert seen == [
        ("GET", "/kb", b""),
        ("POST", "/kb", b'{"kb_id":"support","description":"Support","extraction_enabled":false}'),
        ("PATCH", "/kb/support", b'{"description":"Updated"}'),
        ("DELETE", "/kb/support", b""),
        ("GET", "/kb/support/documents", b""),
        ("GET", "/kb/support/documents/doc-1/chunks", b""),
        ("DELETE", "/kb/support/documents/doc-1", b""),
        ("POST", "/evaluations", b'{"kb_id":"support"}'),
    ]
