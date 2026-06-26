"""Unit tests for agent_scope/tenant_scope routing changes — no real DB."""

from __future__ import annotations

from fleetent.tenant_router import AgentScope, KbScope


def test_agent_scope_does_not_have_open_agent_memory_db() -> None:
    assert not hasattr(AgentScope, "open_agent_memory_db"), (
        "AgentScope must NOT expose open_agent_memory_db — agent memory now uses state_db"
    )


def test_agent_scope_does_not_have_open_agent_memory_db_ro() -> None:
    assert not hasattr(AgentScope, "open_agent_memory_db_ro"), (
        "AgentScope must NOT expose open_agent_memory_db_ro — agent memory now uses state_db"
    )


def test_agent_scope_does_not_have_agent_memory_db_field() -> None:
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(AgentScope)}
    assert "agent_memory_db" not in field_names, (
        "AgentScope must NOT have agent_memory_db field — consolidated into state_db"
    )


def test_agent_scope_exposes_only_shared_vector_backend() -> None:
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(AgentScope)}
    assert field_names == {"state_db", "vector_backend"}


def test_kb_scope_does_not_have_open_shared_memory_db() -> None:
    assert not hasattr(KbScope, "open_shared_memory_db"), (
        "KbScope must NOT have open_shared_memory_db — agent memory moved to AgentScope"
    )


def test_kb_scope_does_not_have_open_shared_memory_db_ro() -> None:
    assert not hasattr(KbScope, "open_shared_memory_db_ro"), (
        "KbScope must NOT have open_shared_memory_db_ro — agent memory moved to AgentScope"
    )
