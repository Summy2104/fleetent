"""Resolution of tenant-default / agent-override context policies."""

from fleetent.intelligence import long_term_ctx_policy as policy


def _record(
    tenant_id: str, agent_id: str | None, **overrides: object
) -> policy.ContextPolicyRecord:
    fields: dict[str, object] = dict(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_memory_enabled=True,
        tenant_shared_memory_enabled=False,
        team_shared_memory_enabled=False,
        knowledge_base_enabled=True,
        user_memory_max_tokens=1024,
        user_memory_top_k=10,
        tenant_shared_memory_max_tokens=512,
        tenant_shared_memory_top_k=5,
        team_shared_memory_max_tokens=512,
        team_shared_memory_top_k=5,
        knowledge_base_max_tokens=1024,
        knowledge_base_top_k=10,
        conflict_preference="auto",
    )
    fields.update(overrides)
    return policy.ContextPolicyRecord(**fields)  # type: ignore[arg-type]


def _sources(resolved: policy.ContextPolicy) -> dict[str, policy.ContextPolicySourceBudget]:
    return {source.source: source for source in resolved.sources}


def test_resolve_default_when_no_policy(monkeypatch):
    monkeypatch.setattr(policy, "get_policy", lambda tenant_id, agent_id: None)
    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")

    resolved = policy.resolve_context_policy(identity)

    assert resolved.tenant_id == "acme"
    assert resolved.agent_id == "a1"
    assert resolved.agent_team_id == "support"
    sources = _sources(resolved)
    assert sources["user_memory"].enabled is True
    assert sources["knowledge_base"].enabled is True
    assert sources["tenant_shared_memory"].enabled is False
    assert sources["team_shared_memory"].enabled is False


def test_resolve_uses_tenant_default_when_no_agent_row(monkeypatch):
    tenant_row = _record("acme", None, tenant_shared_memory_enabled=True)
    monkeypatch.setattr(
        policy,
        "get_policy",
        lambda tenant_id, agent_id: tenant_row if agent_id is None else None,
    )
    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id=None)

    resolved = policy.resolve_context_policy(identity)

    assert _sources(resolved)["tenant_shared_memory"].enabled is True


def test_agent_policy_overrides_tenant_policy(monkeypatch):
    tenant_row = _record(
        "acme", None, tenant_shared_memory_enabled=True, knowledge_base_enabled=True
    )
    agent_row = _record(
        "acme",
        "a1",
        tenant_shared_memory_enabled=False,
        team_shared_memory_enabled=True,
        knowledge_base_enabled=False,
    )

    def fake_get(tenant_id: str, agent_id: str | None):
        return agent_row if agent_id == "a1" else tenant_row

    monkeypatch.setattr(policy, "get_policy", fake_get)
    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id="support")

    resolved = policy.resolve_context_policy(identity)

    sources = _sources(resolved)
    assert sources["tenant_shared_memory"].enabled is False
    assert sources["team_shared_memory"].enabled is True
    assert sources["knowledge_base"].enabled is False


def test_resolve_carries_per_source_budgets(monkeypatch):
    agent_row = _record(
        "acme",
        "a1",
        knowledge_base_max_tokens=777,
        knowledge_base_top_k=3,
    )
    monkeypatch.setattr(policy, "get_policy", lambda tenant_id, agent_id: agent_row)
    identity = policy.AgentContextIdentity(agent_id="a1", tenant_id="acme", team_id=None)

    resolved = policy.resolve_context_policy(identity)

    kb = _sources(resolved)["knowledge_base"]
    assert kb.max_tokens == 777
    assert kb.top_k == 3
