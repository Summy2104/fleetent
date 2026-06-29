from __future__ import annotations

import httpx

from fleetent import long_term_ctx
from fleetent.identity import Principal


async def test_http_knowledge_provider_reads_from_kb_service(tmp_path, monkeypatch) -> None:
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.serve import KBServeConfig, create_app
    from fleetent.tenant_router import SQLiteTenantBackend

    tenant_id = "tenant-a"
    kb_id = "kb-1"
    keyword = "KB-SERVICE-BEACON-4242"
    management_db = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{management_db}")
    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")

    scope = SQLiteTenantBackend(data_dir=tmp_path).resolve(tenant_id)
    scope.open_kb_db(KB_MIGRATIONS)

    old_db = kb_runtime._kb_db
    old_backend = kb_runtime._kb_vector_backend
    try:
        kb_runtime.set_database(scope.kb_db)
        kb_runtime.set_vector_backend(scope.kb_vector_backend)
        await kb_runtime.ingest_text(
            filename="beacon.txt",
            content=f"Remote service retrieval sentinel {keyword}.",
            tenant_id=tenant_id,
            kb_id=kb_id,
            source="e2e-test",
        )
    finally:
        kb_runtime.set_database(old_db)
        kb_runtime.set_vector_backend(old_backend)

    app = create_app(
        KBServeConfig(
            tenant_id=tenant_id,
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
        )
    )
    provider = long_term_ctx.HttpKnowledgeProvider(
        "http://testserver/search",
        service_key="svc-test",
        transport=httpx.ASGITransport(app=app),
    )

    chunks = await provider(
        Principal(user_id="user-1", tenant_id=tenant_id),
        keyword,
        [kb_id],
        5,
        None,
    )

    assert chunks
    assert any(keyword in chunk.content for chunk in chunks)
    assert {chunk.kb_id for chunk in chunks} == {kb_id}
