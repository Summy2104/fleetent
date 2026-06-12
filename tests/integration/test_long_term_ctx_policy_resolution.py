"""Resolution of tenant-default / agent-override context policies."""

import fleetent.agent_store as agent_store
from fleetent.long_term_ctx import _policy as policy
from fleetent.platform.tenancy import store as tenancy_store


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


def _patch_policy_db(monkeypatch, tmp_path):
    from pathlib import Path

    from fleetent.db import create_database
    from tests.integration.test_migrations import apply_migrations

    db_path = Path(tmp_path) / "policy.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(policy, "_database", lambda: database)


def _seed_policy_scope(tenant_id: str, agent_id: str | None = None) -> None:
    tenancy_store.create_tenant(id=tenant_id, name=tenant_id.title())
    if agent_id is not None:
        agent_store.create_agent(agent_id, "prompt", [], tenant_id=tenant_id)


def test_upsert_then_get_round_trips_tenant_default(monkeypatch, tmp_path):
    _patch_policy_db(monkeypatch, tmp_path)
    _seed_policy_scope("acme")

    policy.upsert_policy(_record("acme", None, tenant_shared_memory_enabled=True))

    loaded = policy.get_policy("acme", None)

    assert loaded is not None
    assert loaded.agent_id is None
    assert loaded.tenant_shared_memory_enabled is True
    assert loaded.knowledge_base_max_tokens == 1024


def test_upsert_replaces_existing_scope_on_conflict(monkeypatch, tmp_path):
    _patch_policy_db(monkeypatch, tmp_path)
    _seed_policy_scope("acme", "a1")

    policy.upsert_policy(_record("acme", "a1", knowledge_base_max_tokens=100))
    policy.upsert_policy(_record("acme", "a1", knowledge_base_max_tokens=999))

    loaded = policy.get_policy("acme", "a1")

    assert loaded is not None
    assert loaded.agent_id == "a1"
    assert loaded.knowledge_base_max_tokens == 999


def test_get_policy_returns_none_when_missing(monkeypatch, tmp_path):
    _patch_policy_db(monkeypatch, tmp_path)

    assert policy.get_policy("acme", "ghost") is None


def test_upsert_rejects_invalid_record_before_write(monkeypatch, tmp_path):
    import pytest

    _patch_policy_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="tenant_id"):
        policy.upsert_policy(_record("", None))


def test_database_factory_builds_sqlite_database():
    from fleetent.db import SQLiteDatabase

    assert isinstance(policy._database(), SQLiteDatabase)
