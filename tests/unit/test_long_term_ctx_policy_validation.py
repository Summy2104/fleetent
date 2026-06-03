"""Validation rules for stored long-term context policy records."""

import dataclasses

import pytest

from fleetent.intelligence import long_term_ctx_policy as policy


def _record(**overrides: object) -> policy.ContextPolicyRecord:
    fields: dict[str, object] = dict(
        tenant_id="acme",
        agent_id=None,
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


def test_valid_record_passes():
    policy.validate_policy_record(_record())


def test_empty_tenant_id_fails_fast():
    with pytest.raises(ValueError, match="tenant_id"):
        policy.validate_policy_record(_record(tenant_id=""))


def test_whitespace_tenant_id_fails_fast():
    with pytest.raises(ValueError, match="tenant_id"):
        policy.validate_policy_record(_record(tenant_id="   "))


def test_empty_agent_override_fails_fast():
    with pytest.raises(ValueError, match="agent_id"):
        policy.validate_policy_record(_record(agent_id=""))


@pytest.mark.parametrize(
    "field",
    [
        "user_memory_max_tokens",
        "tenant_shared_memory_max_tokens",
        "team_shared_memory_max_tokens",
        "knowledge_base_max_tokens",
    ],
)
def test_negative_budget_fails_fast(field):
    with pytest.raises(ValueError, match=field):
        policy.validate_policy_record(_record(**{field: -1}))


@pytest.mark.parametrize(
    "field",
    [
        "user_memory_top_k",
        "tenant_shared_memory_top_k",
        "team_shared_memory_top_k",
        "knowledge_base_top_k",
    ],
)
def test_negative_top_k_fails_fast(field):
    with pytest.raises(ValueError, match=field):
        policy.validate_policy_record(_record(**{field: -1}))


def test_invalid_conflict_preference_fails_fast():
    with pytest.raises(ValueError, match="conflict_preference"):
        policy.validate_policy_record(_record(conflict_preference="newest"))


def test_record_exposes_no_arbitrary_shared_memory_scope():
    # Shared Memory scope is derived from agent ownership, never named by policy,
    # so the stored record must not carry a free-form scope grant field.
    names = {f.name for f in dataclasses.fields(policy.ContextPolicyRecord)}
    assert not {"scope", "scope_id", "scope_type", "shared_memory_scope"} & names
    assert "tenant_shared_memory_enabled" in names
    assert "team_shared_memory_enabled" in names
