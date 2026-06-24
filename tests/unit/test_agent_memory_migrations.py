"""Unit tests: agent_memory_items DDL lives in AGENT_STATE_MIGRATIONS (no real DB)."""

from __future__ import annotations

import importlib


def test_agent_memory_migrations_module_removed() -> None:
    """The standalone agent_memory_migrations module must not exist."""
    try:
        importlib.import_module("fleetent.memory.agent_memory_migrations")
        raise AssertionError(
            "fleetent.memory.agent_memory_migrations must be removed"
            " — DDL moved to agent_state_migrations"
        )
    except ModuleNotFoundError:
        pass


def test_agent_state_migrations_creates_agent_memory_items() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    all_sql = " ".join(sql for _, sql in MIGRATIONS).lower()
    assert "agent_memory_items" in all_sql, (
        "AGENT_STATE_MIGRATIONS must create agent_memory_items table"
    )


def test_agent_memory_items_has_no_scope_columns() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    all_sql = " ".join(sql for _, sql in MIGRATIONS).lower()
    assert "scope_type" not in all_sql
    assert "scope_id" not in all_sql


def test_agent_memory_items_has_required_columns() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    create_stmts = [
        sql
        for _, sql in MIGRATIONS
        if "agent_memory_items" in sql.lower() and "create table" in sql.lower()
    ]
    assert create_stmts, "no CREATE TABLE for agent_memory_items in AGENT_STATE_MIGRATIONS"
    ddl = create_stmts[0].lower()
    for col in ("id", "type", "content", "status", "source", "created_by", "created_at", "updated_at"):
        assert col in ddl, f"missing column '{col}' in agent_memory_items DDL"


def test_no_shared_memory_items_table_in_agent_state_migrations() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    all_sql = " ".join(sql for _, sql in MIGRATIONS).lower()
    assert "shared_memory_items" not in all_sql, (
        "old shared_memory_items must not appear in agent_state migrations"
    )
