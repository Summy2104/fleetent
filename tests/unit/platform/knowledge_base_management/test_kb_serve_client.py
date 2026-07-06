from __future__ import annotations

import httpx
import pytest

from fleetent.config import Settings
from fleetent.platform.knowledge_base_management.auth import resolve_service_key_ref
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


def test_resolve_auth_ref_supports_env_and_file_refs(tmp_path, monkeypatch) -> None:
    key_path = tmp_path / "kb-service-key"
    key_path.write_text("svc-from-file", encoding="utf-8")
    monkeypatch.setenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", "svc-from-env")

    assert resolve_service_key_ref("env:FLEETENT_PLATFORM_KB_SERVICE_KEY") == "svc-from-env"
    assert resolve_service_key_ref(f"file://{key_path}") == "svc-from-file"


def test_resolve_auth_ref_raises_for_missing_env(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", raising=False)

    with pytest.raises(ValueError, match="kb service key env var is missing"):
        resolve_service_key_ref("env:FLEETENT_PLATFORM_KB_SERVICE_KEY")


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


def test_upload_document_sends_multipart_and_preserves_serve_errors(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_PLATFORM_KB_SERVICE_KEY", "svc-test")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/kb/support/documents":
            assert request.method == "POST"
            assert request.headers["Authorization"] == "Bearer svc-test"
            assert request.headers["X-Fleetent-Principal"] == (
                '{"user_id":"platform","tenant_id":"tenant-a"}'
            )
            assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
            assert b'filename="guide.md"' in request.content
            assert b"hello world" in request.content
            return httpx.Response(200, json={"job_id": "job-1"})
        if request.url.path == "/kb/missing/documents":
            return httpx.Response(404, json={"detail": "kb not found"}, request=request)
        return httpx.Response(
            413,
            json={"detail": "upload exceeds max_upload_bytes"},
            request=request,
        )

    client = KBServeClient(
        KBServeSettings(
            url="http://kb-serve.test",
            service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert client.upload_document(
        "tenant-a",
        "support",
        filename="guide.md",
        content=b"hello world",
        content_type="text/markdown",
    ) == {"job_id": "job-1"}

    with pytest.raises(httpx.HTTPStatusError) as missing_exc:
        client.upload_document(
            "tenant-a",
            "missing",
            filename="guide.md",
            content=b"hello world",
            content_type="text/markdown",
        )
    assert missing_exc.value.response.status_code == 404

    with pytest.raises(httpx.HTTPStatusError) as too_large_exc:
        client.upload_document(
            "tenant-a",
            "too-large",
            filename="guide.md",
            content=b"hello world",
            content_type="text/markdown",
        )
    assert too_large_exc.value.response.status_code == 413


def test_get_kb_serve_client_returns_503_when_key_unresolvable(monkeypatch):
    """An unset key env must surface as a clear 503 (like missing url/ref), not a
    500 from _resolve_auth_ref deep inside a request — this is the exact failure
    when the platform process started before the dev key file existed."""
    import pytest
    from fastapi import HTTPException

    from fleetent.config import KBServeSettings
    from fleetent.platform.knowledge_base_management import kb_admin_api

    monkeypatch.delenv("MISSING_KB_KEY_ENV", raising=False)
    monkeypatch.setattr(
        kb_admin_api,
        "Settings",
        lambda: type(
            "S",
            (),
            {
                "kb_serve": KBServeSettings(
                    url="http://127.0.0.1:8768",
                    service_key_ref="env:MISSING_KB_KEY_ENV",
                )
            },
        )(),
    )

    with pytest.raises(HTTPException) as exc:
        kb_admin_api.get_kb_serve_client()

    assert exc.value.status_code == 503
    assert "key" in exc.value.detail.lower()
