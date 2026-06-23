"""E2E tests for the KB ingest → retrieval → agent injection → audit chain.

Three levels:
  E2E-1  Direct chain: ingest + search entirely in-process (no managed stack).
  E2E-2  Injection:    KB content must appear in the system message the agent
                       sends to the LLM stub.
  E2E-3  Audit trace:  a kb_retrieval trace event must be written to the
                       agent-side state DB after KB content is retrieved.
"""
from __future__ import annotations

import httpx

from tests.e2e._entrypoint_smoke import wait_for_condition
from tests.e2e._kb_helpers import (
    KB_BEACON_KEYWORD,
    KB_BEACON_TEXT,
    ManagedKBStack,
    clear_stub_requests,
    find_system_messages_containing,
    get_stub_requests,
    managed_kb_stack,  # noqa: F401 — fixture import
    wait_for_kb_trace,
)

# Re-export managed_kb_stack so pytest discovers it as a fixture in this module.
__all__ = ["managed_kb_stack"]


# ---------------------------------------------------------------------------
# E2E-1  Direct ingest → search (no managed stack)
# ---------------------------------------------------------------------------


async def test_kb_ingest_and_search_direct(tmp_path):
    """Ingest beacon text and retrieve it via vector search — all in-process."""
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend

    data_dir = tmp_path / "kb-data"
    scope = SQLiteTenantBackend(data_dir=data_dir).resolve("e2e-direct")
    scope.open_kb_db(KB_MIGRATIONS)

    old_db = kb_runtime._kb_db
    old_backend = kb_runtime._kb_vector_backend
    try:
        kb_runtime.set_database(scope.kb_db)
        kb_runtime.set_vector_backend(scope.kb_vector_backend)

        await kb_runtime.ingest_text(
            filename="beacon.txt",
            content=KB_BEACON_TEXT,
            tenant_id="e2e-direct",
            kb_id="direct-kb",
            source="e2e-test",
        )

        results = await kb_runtime.search(
            KB_BEACON_KEYWORD,
            tenant_id="e2e-direct",
            kb_ids=["direct-kb"],
            limit=5,
            mode="vector",
        )
    finally:
        kb_runtime.set_database(old_db)
        kb_runtime.set_vector_backend(old_backend)

    assert len(results) > 0, "vector search returned no results after ingest"
    all_content = " ".join(r.content for r in results)
    assert KB_BEACON_KEYWORD in all_content, (
        f"beacon keyword not found in retrieved chunks:\n{all_content}"
    )


# ---------------------------------------------------------------------------
# E2E-2  KB content injected into agent system message
# ---------------------------------------------------------------------------


def test_kb_content_injected_into_agent_prompt(managed_kb_stack: ManagedKBStack) -> None:
    """After a chat turn the LLM stub must receive the KB beacon in a system message."""
    clear_stub_requests(managed_kb_stack.stub_v1_url)

    with httpx.stream(
        "POST",
        f"{managed_kb_stack.platform_url}/admin/agents/{managed_kb_stack.agent_name}/chat",
        headers=managed_kb_stack.admin_session_headers,
        json={"message": f"What is {KB_BEACON_KEYWORD}?"},
        timeout=20.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200, f"chat request failed:\n{body.decode()}"

    def _check():
        hits = find_system_messages_containing(
            get_stub_requests(managed_kb_stack.stub_v1_url), KB_BEACON_KEYWORD
        )
        return hits if hits else None

    hits = wait_for_condition(
        _check,
        timeout=10.0,
        interval=0.3,
        description=f"KB beacon '{KB_BEACON_KEYWORD}' in LLM stub system message",
    )
    assert hits, "KB beacon not found in any system message sent to LLM stub"


# ---------------------------------------------------------------------------
# E2E-3  KB retrieval audit trace recorded in agent state DB
# ---------------------------------------------------------------------------


def test_kb_retrieval_audit_trace_recorded(managed_kb_stack: ManagedKBStack) -> None:
    """After a chat turn a kb_retrieval trace must exist in the agent state DB."""
    with httpx.stream(
        "POST",
        f"{managed_kb_stack.platform_url}/admin/agents/{managed_kb_stack.agent_name}/chat",
        headers=managed_kb_stack.admin_session_headers,
        json={"message": f"Tell me about {KB_BEACON_KEYWORD}"},
        timeout=20.0,
    ) as response:
        b"".join(response.iter_bytes())

    assert response.status_code == 200

    traces = wait_for_kb_trace(
        managed_kb_stack.home_dir,
        managed_kb_stack.agent_name,
        timeout=10.0,
    )
    assert len(traces) > 0, "no kb_retrieval traces found in agent state DB"

    trace = traces[0]
    assert trace["hit_count"] > 0, f"trace has zero hits: {trace}"
    assert managed_kb_stack.kb_id in trace["kb_ids"], (
        f"expected kb_id '{managed_kb_stack.kb_id}' in trace kb_ids: {trace['kb_ids']}"
    )
