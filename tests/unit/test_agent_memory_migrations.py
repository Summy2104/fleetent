"""Unit tests for agent_memory_migrations — DDL structure inspection only (no real DB)."""

from __future__ import annotations

import importlib


def test_agent_memory_migrations_module_exists() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory_migrations")
    assert hasattr(module, "MIGRATIONS")


def test_migrations_create_agent_memory_items_table() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory_migrations")
    migrations: list[tuple[int, str]] = module.MIGRATIONS
    all_sql = " ".join(sql for _, sql in migrations).lower()
    assert "agent_memory_items" in all_sql, "MIGRATIONS must create agent_memory_items table"


def test_agent_memory_items_has_no_scope_columns() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory_migrations")
    migrations: list[tuple[int, str]] = module.MIGRATIONS
    all_sql = " ".join(sql for _, sql in migrations).lower()
    assert "scope_type" not in all_sql, "agent_memory_items must not have scope_type column"
    assert "scope_id" not in all_sql, "agent_memory_items must not have scope_id column"


def test_agent_memory_items_has_required_columns() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory_migrations")
    migrations: list[tuple[int, str]] = module.MIGRATIONS
    create_stmts = [sql for _, sql in migrations if "create table" in sql.lower()]
    assert create_stmts, "no CREATE TABLE statement found"
    create_sql = create_stmts[0].lower()
    for col in ("id", "type", "content", "status", "source", "created_by", "created_at", "updated_at"):
        assert col in create_sql, f"expected column '{col}' in agent_memory_items DDL"


def test_no_shared_memory_items_table_in_migrations() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory_migrations")
    migrations: list[tuple[int, str]] = module.MIGRATIONS
    all_sql = " ".join(sql for _, sql in migrations).lower()
    assert "shared_memory_items" not in all_sql, "old shared_memory_items must not appear in agent migrations"
