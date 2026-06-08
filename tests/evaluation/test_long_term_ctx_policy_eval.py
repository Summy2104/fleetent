"""Deterministic evaluation of long-term context policy resolution + building.

Covers tenant-default behavior, agent override, Shared Memory disabled by
default, and the no-cross-tenant / no-cross-team isolation guarantee. Uses the
real policy + shared-memory stores against a tmp database with a deterministic
in-memory vector store (no real LLM / embedding service).
"""

from fleetent.intelligence import long_term_ctx
from fleetent.intelligence import long_term_ctx_policy as policy
from fleetent.vector_store import SearchResult
from tests.integration.test_migrations import apply_migrations

SEED = [
    ("tenant", "acme", "Acme tenant policy: refunds within 30 days"),
    ("team", "support", "Support team runbook: rotate on-call weekly"),
    ("tenant", "globex", "Globex tenant secret: do not disclose"),
    ("team", "sales", "Sales team quota: close by quarter end"),
]


def _record(tenant_id, agent_id, **overrides):
    fields = dict(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_memory_enabled=True,
        tenant_shared_memory_enabled=False,
        team_shared_memory_enabled=False,
        knowledge_base_enabled=False,
        user_memory_max_tokens=1024,
        user_memory_top_k=10,
        tenant_shared_memory_max_tokens=1024,
        tenant_shared_memory_top_k=10,
        team_shared_memory_max_tokens=1024,
        team_shared_memory_top_k=10,
        knowledge_base_max_tokens=1024,
        knowledge_base_top_k=10,
        conflict_preference="auto",
    )
    fields.update(overrides)
    return policy.ContextPolicyRecord(**fields)


async def test_long_term_ctx_policy_evaluation(monkeypatch, tmp_path):
    from fleetent.intelligence import memory
    from fleetent.intelligence.memory import shared

    db_path = tmp_path / "policy-eval.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    indexed: dict[str, tuple[str, str]] = {}

    async def upsert(id: str, text: str, namespace: str) -> None:
        indexed[id] = (text, namespace)

    async def delete(id: str, namespace: str) -> None:
        indexed.pop(id, None)

    async def search(query: str, namespace: str, limit: int = 10) -> list[SearchResult]:
        return [
            SearchResult(id=item_id, score=1.0)
            for item_id, (_text, item_namespace) in indexed.items()
            if item_namespace == namespace
        ][:limit]

    monkeypatch.setattr(shared.vector_store, "upsert", upsert)
    monkeypatch.setattr(shared.vector_store, "delete", delete)
    monkeypatch.setattr(shared.vector_store, "search", search)

    async def empty_user_memory(user_id, query, limit=10):
        return []

    async def empty_knowledge(user_id, query, agent_id, limit):
        return []

    monkeypatch.setattr(long_term_ctx.memory, "search", empty_user_memory)
    long_term_ctx.set_knowledge_provider(empty_knowledge)

    for scope_type, scope_id, content in SEED:
        await memory.create_shared_memory(
            scope_type=scope_type,
            scope_id=scope_id,
            type="context",
            content=content,
            created_by="eval",
        )

    agent = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")

    # Case 1: no policy -> Shared Memory disabled by default; UM + KB only.
    default = await long_term_ctx.build_context_with_policy(
        identity=agent, user_id="u1", query="refunds", available_tokens=2000
    )
    assert not [s for s in default.sources if "shared_memory" in s.source_type]
    default_reasons = {(d.source_type, d.reason) for d in default.budget_metadata.decisions}
    assert ("tenant_shared_memory", "disabled_by_policy") in default_reasons
    assert ("team_shared_memory", "disabled_by_policy") in default_reasons

    # Case 2: agent override enabling tenant + team Shared Memory.
    policy.upsert_policy(
        _record("acme", "a1", tenant_shared_memory_enabled=True, team_shared_memory_enabled=True)
    )
    enabled = await long_term_ctx.build_context_with_policy(
        identity=agent, user_id="u1", query="policy", available_tokens=2000
    )
    contents = enabled.text
    # Sees its own tenant + team scopes ...
    assert "Acme tenant policy" in contents
    assert "Support team runbook" in contents
    # ... and never another tenant's or another team's Shared Memory.
    assert "Globex tenant secret" not in contents
    assert "Sales team quota" not in contents
