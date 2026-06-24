"""Unit tests for agent_scope/tenant_scope routing changes — no real DB."""

from __future__ import annotations

import inspect

from fleetent.tenant_router import AgentScope, KbScope


def test_agent_scope_has_open_agent_memory_db() -> None:
    assert hasattr(AgentScope, "open_agent_memory_db"), (
        "AgentScope must expose open_agent_memory_db"
    )


def test_agent_scope_open_agent_memory_db_accepts_migrations() -> None:
    sig = inspect.signature(AgentScope.open_agent_memory_db)
    assert "migrations" in sig.parameters


def test_agent_scope_has_open_agent_memory_db_ro() -> None:
    assert hasattr(AgentScope, "open_agent_memory_db_ro"), (
        "AgentScope must expose open_agent_memory_db_ro for platform read-projection"
    )


def test_kb_scope_does_not_have_open_shared_memory_db() -> None:
    assert not hasattr(KbScope, "open_shared_memory_db"), (
        "KbScope must NOT have open_shared_memory_db — agent memory moved to AgentScope"
    )


def test_kb_scope_does_not_have_open_shared_memory_db_ro() -> None:
    assert not hasattr(KbScope, "open_shared_memory_db_ro"), (
        "KbScope must NOT have open_shared_memory_db_ro — agent memory moved to AgentScope"
    )
