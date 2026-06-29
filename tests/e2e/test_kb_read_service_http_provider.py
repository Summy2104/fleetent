from __future__ import annotations

import httpx

from fleetent import long_term_ctx
from fleetent.identity import Principal
from tests.e2e._entrypoint_smoke import wait_for_condition
from tests.e2e._kb_helpers import (
    KB_BEACON_KEYWORD,
    ManagedKBStack,
    clear_stub_requests,
    find_system_messages_containing,
    get_stub_requests,
    managed_kb_http_stack,  # noqa: F401 - fixture import
)

__all__ = ["managed_kb_http_stack"]


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
    async with app.router.lifespan_context(app):
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


def test_managed_stack_agent_reads_kb_via_http_provider(
    managed_kb_http_stack: ManagedKBStack,
) -> None:
    clear_stub_requests(managed_kb_http_stack.stub_v1_url)

    with httpx.stream(
        "POST",
        f"{managed_kb_http_stack.platform_url}/admin/agents/{managed_kb_http_stack.agent_name}/chat",
        headers=managed_kb_http_stack.admin_session_headers,
        json={"message": f"What is {KB_BEACON_KEYWORD}?"},
        timeout=20.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200, f"chat request failed:\n{body.decode()}"

    def _check():
        hits = find_system_messages_containing(
            get_stub_requests(managed_kb_http_stack.stub_v1_url), KB_BEACON_KEYWORD
        )
        return hits if hits else None

    hits = wait_for_condition(
        _check,
        timeout=10.0,
        interval=0.3,
        description=f"HTTP KB beacon '{KB_BEACON_KEYWORD}' in LLM stub system message",
    )
    assert hits
