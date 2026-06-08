"""Tests for the long-term context policy store on the unified db runtime.

Schema is created by Alembic migrations against a tmp_path database, isolated
via the DATABASE_URL env var (named params, wide tenant/agent policy rows).
"""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.long_term_ctx import _policy as policy


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


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


def test_migration_creates_policy_table(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(long_term_context_policies)")}
    conn.close()
    assert "long_term_context_policies" in tables
    assert {
        "id",
        "tenant_id",
        "agent_id",
        "user_memory_enabled",
        "tenant_shared_memory_enabled",
        "team_shared_memory_enabled",
        "knowledge_base_enabled",
        "user_memory_max_tokens",
        "user_memory_top_k",
        "tenant_shared_memory_max_tokens",
        "tenant_shared_memory_top_k",
        "team_shared_memory_max_tokens",
        "team_shared_memory_top_k",
        "knowledge_base_max_tokens",
        "knowledge_base_top_k",
        "conflict_preference",
        "created_at",
        "updated_at",
    } <= cols


def test_upsert_and_get_tenant_default_row(store_db):
    policy.upsert_policy(_record("acme", None, tenant_shared_memory_enabled=True))
    loaded = policy.get_policy("acme", None)
    assert loaded is not None
    assert loaded.tenant_id == "acme"
    assert loaded.agent_id is None
    assert loaded.tenant_shared_memory_enabled is True
    assert loaded.knowledge_base_enabled is True


def test_upsert_and_get_agent_override_row(store_db):
    policy.upsert_policy(_record("acme", None))
    policy.upsert_policy(_record("acme", "agent-1", team_shared_memory_enabled=True))
    tenant_row = policy.get_policy("acme", None)
    agent_row = policy.get_policy("acme", "agent-1")
    assert tenant_row is not None and tenant_row.agent_id is None
    assert agent_row is not None and agent_row.agent_id == "agent-1"
    assert agent_row.team_shared_memory_enabled is True


def test_upsert_is_idempotent_per_scope(store_db):
    policy.upsert_policy(_record("acme", None, user_memory_max_tokens=1024))
    policy.upsert_policy(_record("acme", None, user_memory_max_tokens=2048))
    loaded = policy.get_policy("acme", None)
    assert loaded is not None
    assert loaded.user_memory_max_tokens == 2048


def test_get_policy_missing_returns_none(store_db):
    assert policy.get_policy("acme", None) is None
    assert policy.get_policy("acme", "agent-x") is None
