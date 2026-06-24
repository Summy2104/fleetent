"""Unit tests: AGENT_STATE_MIGRATIONS must contain agent_memory_items DDL (no real DB)."""

from __future__ import annotations


def test_agent_state_migrations_creates_agent_memory_items() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    all_sql = " ".join(sql for _, sql in MIGRATIONS).lower()
    assert "agent_memory_items" in all_sql, (
        "AGENT_STATE_MIGRATIONS must create agent_memory_items table"
    )


def test_agent_memory_items_has_no_scope_columns_in_state_migrations() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    all_sql = " ".join(sql for _, sql in MIGRATIONS).lower()
    assert "scope_type" not in all_sql
    assert "scope_id" not in all_sql


def test_agent_memory_items_required_columns_in_state_migrations() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    create_stmts = [
        sql
        for _, sql in MIGRATIONS
        if "agent_memory_items" in sql.lower() and "create table" in sql.lower()
    ]
    assert create_stmts, "no CREATE TABLE for agent_memory_items found in AGENT_STATE_MIGRATIONS"
    ddl = create_stmts[0].lower()
    for col in (
        "id",
        "type",
        "content",
        "status",
        "source",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert col in ddl, f"missing column '{col}' in agent_memory_items DDL"
