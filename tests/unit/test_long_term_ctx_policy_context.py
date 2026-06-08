"""Policy-aware long-term context building (Shared Memory integration)."""

from datetime import UTC, datetime

from fleetent import long_term_ctx
from fleetent.long_term_ctx import _policy as policy
from fleetent.memory.models import SharedMemoryItem


def _record(
    tenant_id: str, agent_id: str | None, **overrides: object
) -> policy.ContextPolicyRecord:
    fields: dict[str, object] = dict(
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
    return policy.ContextPolicyRecord(**fields)  # type: ignore[arg-type]


def _shared_item(item_id: str, scope_type: str, scope_id: str, content: str) -> SharedMemoryItem:
    now = datetime.now(UTC).replace(microsecond=0)
    return SharedMemoryItem(
        id=item_id,
        scope_type=scope_type,  # type: ignore[arg-type]
        scope_id=scope_id,
        type="context",
        content=content,
        status="active",
        source="manual",
        source_ref=None,
        created_by="admin",
        created_at=now,
        updated_at=now,
    )


async def _empty_memory_search(user_id, query, limit=10):
    return []


def _use_record(monkeypatch, record: policy.ContextPolicyRecord) -> None:
    monkeypatch.setattr(
        policy, "get_policy", lambda tenant_id, agent_id: record if agent_id is None else None
    )


async def test_enabled_tenant_shared_memory_is_queried_by_tenant_scope(monkeypatch):
    _use_record(monkeypatch, _record("acme", None, tenant_shared_memory_enabled=True))
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    calls = []

    async def fake_search_shared(scope_type, scope_id, query, limit=10):
        calls.append((scope_type, scope_id, query, limit))
        return [_shared_item("s1", scope_type, scope_id, "Escalate priority tickets in 1h")]

    monkeypatch.setattr(long_term_ctx.memory, "search_shared_memory", fake_search_shared)

    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")
    built = await long_term_ctx.build_context_with_policy(
        identity=identity,
        user_id="user-1",
        query="how to escalate?",
        available_tokens=1000,
    )

    assert ("tenant", "acme", "how to escalate?", 10) in calls
    assert "Escalate priority tickets in 1h" in built.text
    shared_sources = [s for s in built.sources if s.source_type == "tenant_shared_memory"]
    assert shared_sources and shared_sources[0].source_id == "s1"


async def test_disabled_tenant_shared_memory_is_not_queried(monkeypatch):
    _use_record(monkeypatch, _record("acme", None, tenant_shared_memory_enabled=False))
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    async def fail_search_shared(scope_type, scope_id, query, limit=10):
        raise AssertionError("shared memory should not be queried when disabled")

    monkeypatch.setattr(long_term_ctx.memory, "search_shared_memory", fail_search_shared)

    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")
    built = await long_term_ctx.build_context_with_policy(
        identity=identity,
        user_id="user-1",
        query="anything",
        available_tokens=1000,
    )

    reasons = {(d.source_type, d.reason) for d in built.budget_metadata.decisions}
    assert ("tenant_shared_memory", "disabled_by_policy") in reasons


async def test_enabled_team_shared_memory_is_queried_by_team_scope(monkeypatch):
    _use_record(monkeypatch, _record("acme", None, team_shared_memory_enabled=True))
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    calls = []

    async def fake_search_shared(scope_type, scope_id, query, limit=10):
        calls.append((scope_type, scope_id))
        return [_shared_item("t1", scope_type, scope_id, "Team runbook: rotate on-call weekly")]

    monkeypatch.setattr(long_term_ctx.memory, "search_shared_memory", fake_search_shared)

    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")
    built = await long_term_ctx.build_context_with_policy(
        identity=identity,
        user_id="user-1",
        query="oncall?",
        available_tokens=1000,
    )

    assert ("team", "support") in calls
    sources = [s for s in built.sources if s.source_type == "team_shared_memory"]
    assert sources and sources[0].source_id == "t1"


async def test_empty_team_id_skips_team_shared_memory_with_decision(monkeypatch):
    _use_record(monkeypatch, _record("acme", None, team_shared_memory_enabled=True))
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    calls = []

    async def fake_search_shared(scope_type, scope_id, query, limit=10):
        calls.append(scope_type)
        return []

    monkeypatch.setattr(long_term_ctx.memory, "search_shared_memory", fake_search_shared)

    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id=None)
    built = await long_term_ctx.build_context_with_policy(
        identity=identity,
        user_id="user-1",
        query="oncall?",
        available_tokens=1000,
    )

    assert "team" not in calls
    reasons = {(d.source_type, d.reason) for d in built.budget_metadata.decisions}
    assert ("team_shared_memory", "team_id_missing") in reasons


async def test_per_source_budget_excludes_overflow(monkeypatch):
    _use_record(
        monkeypatch,
        _record(
            "acme", None, tenant_shared_memory_enabled=True, tenant_shared_memory_max_tokens=20
        ),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    async def fake_search_shared(scope_type, scope_id, query, limit=10):
        return [
            _shared_item("s1", scope_type, scope_id, "first item that fits the small budget"),
            _shared_item("s2", scope_type, scope_id, "second item exceeds remaining budget"),
        ]

    monkeypatch.setattr(long_term_ctx.memory, "search_shared_memory", fake_search_shared)

    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id=None)
    built = await long_term_ctx.build_context_with_policy(
        identity=identity,
        user_id="user-1",
        query="q",
        available_tokens=1000,
    )

    reasons = {(d.source_id, d.reason) for d in built.budget_metadata.decisions}
    assert ("s2", "source_budget_exceeded") in reasons
    assert "s2" not in {s.source_id for s in built.sources}
