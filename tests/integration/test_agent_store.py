"""Tests for agent_store on the unified db runtime.

Schema is created by Alembic migrations against a tmp_path database, isolated via
the DATABASE_URL env var (named params, no legacy _init_db / DB_PATH path).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_create_and_get_agent(db):
    agent_store.create_agent("assistant", "You are helpful.", ["shell", "github__*"])
    found = agent_store.get_by_name("assistant")
    assert found is not None
    assert found.name == "assistant"
    assert found.system_prompt == "You are helpful."
    assert found.allowed_tools == ["shell", "github__*"]


def test_get_by_name_missing(db):
    assert agent_store.get_by_name("nonexistent") is None


def test_duplicate_name_raises(db):
    agent_store.create_agent("assistant", "p1", ["shell"])
    with pytest.raises(Exception, match="UNIQUE constraint"):
        agent_store.create_agent("assistant", "p2", ["shell"])


def test_assign_and_get_agent_for_user(db):
    agent = agent_store.create_agent("assistant", "prompt", ["shell"])
    agent_store.assign_user("user-1", agent.id)
    found = agent_store.get_agent_for_user("user-1")
    assert found is not None
    assert found.id == agent.id


def test_get_agent_for_user_unassigned(db):
    assert agent_store.get_agent_for_user("user-99") is None


# --- agent ownership (tenant_id / team_id) ---


def test_create_agent_defaults_tenant_and_team(db):
    agent = agent_store.create_agent("owned", "prompt", [])
    assert agent.tenant_id == "default"
    assert agent.team_id is None
    found = agent_store.get_by_name("owned")
    assert found is not None
    assert found.tenant_id == "default"
    assert found.team_id is None


def test_create_agent_with_explicit_ownership(db):
    agent = agent_store.create_agent(
        "acme-support", "prompt", [], tenant_id="acme", team_id="support"
    )
    assert agent.tenant_id == "acme"
    assert agent.team_id == "support"
    found = agent_store.get_by_name("acme-support")
    assert found is not None
    assert found.tenant_id == "acme"
    assert found.team_id == "support"


def test_existing_agent_backfills_default_tenant(db):
    # A row inserted without ownership columns (legacy shape) resolves to the
    # migration's tenant_id default and a null team_id.
    from fleetent.config import Settings
    from fleetent.db import create_database

    database = create_database(Settings(anthropic_api_key="").database_url)
    database.execute(
        "INSERT INTO agents (name, system_prompt, allowed_tools, created_at)"
        " VALUES (:name, :system_prompt, :allowed_tools, :created_at)",
        {
            "name": "legacy",
            "system_prompt": "p",
            "allowed_tools": "[]",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )
    found = agent_store.get_by_name("legacy")
    assert found is not None
    assert found.tenant_id == "default"
    assert found.team_id is None


def test_ownership_survives_user_and_channel_lookup(db):
    agent = agent_store.create_agent("routed", "prompt", [], tenant_id="acme", team_id="support")
    agent_store.assign_user("user-1", agent.id)
    agent_store.assign_channel("slack", "C123", agent.id)
    by_user = agent_store.get_agent_for_user("user-1")
    by_channel = agent_store.get_agent_for_channel("slack", "C123")
    assert by_user is not None and by_user.tenant_id == "acme" and by_user.team_id == "support"
    assert by_channel is not None and by_channel.tenant_id == "acme"


# --- channel_agents tests ---


def test_assign_and_get_agent_for_channel(db):
    agent = agent_store.create_agent("ch-agent", "Channel prompt.", [])
    agent_store.assign_channel("slack", "C123", agent.id)
    found = agent_store.get_agent_for_channel("slack", "C123")
    assert found is not None
    assert found.id == agent.id


def test_get_agent_for_channel_unbound(db):
    assert agent_store.get_agent_for_channel("slack", "C999") is None


def test_assign_channel_upserts_on_duplicate(db):
    a1 = agent_store.create_agent("agent-a", "A", [])
    a2 = agent_store.create_agent("agent-b", "B", [])
    agent_store.assign_channel("slack", "C1", a1.id)
    agent_store.assign_channel("slack", "C1", a2.id)
    found = agent_store.get_agent_for_channel("slack", "C1")
    assert found is not None
    assert found.id == a2.id


def test_unassign_channel(db):
    agent = agent_store.create_agent("rm-agent", "R", [])
    agent_store.assign_channel("telegram", "G42", agent.id)
    agent_store.unassign_channel("telegram", "G42")
    assert agent_store.get_agent_for_channel("telegram", "G42") is None


def test_platform_isolation(db):
    agent = agent_store.create_agent("iso-agent", "I", [])
    agent_store.assign_channel("slack", "C5", agent.id)
    assert agent_store.get_agent_for_channel("telegram", "C5") is None


# --- default agent tests ---


def test_get_default_agent_returns_agent_when_configured(db, monkeypatch):
    agent = agent_store.create_agent("basic", "Basic prompt.", [])
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "basic")
    found = agent_store.get_default_agent()
    assert found is not None
    assert found.id == agent.id


def test_get_default_agent_returns_none_when_not_configured(db, monkeypatch):
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: None)
    assert agent_store.get_default_agent() is None


def test_get_default_agent_returns_none_when_agent_missing(db, monkeypatch):
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "nonexistent")
    assert agent_store.get_default_agent() is None
