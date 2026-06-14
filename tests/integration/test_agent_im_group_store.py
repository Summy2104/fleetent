"""Tests for agent_im_group_store and agent_store IM capability switches."""

import pytest

from fleetent import agent_store
from fleetent.platform.agent_management_console import agent_im_group_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_bind_unbind_and_list_im_groups(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])

    store.bind(agent.id, "slack", "C-sales", created_by="admin")
    store.bind(agent.id, "telegram", "-10042", created_by="admin")
    store.bind(agent.id, "slack", "C-sales", created_by="admin")

    assert store.list_groups_for_agent(agent.id) == [
        {"platform": "slack", "group_id": "C-sales"},
        {"platform": "telegram", "group_id": "-10042"},
    ]

    store.unbind(agent.id, "slack", "C-sales")

    assert store.list_groups_for_agent(agent.id) == [{"platform": "telegram", "group_id": "-10042"}]


def test_agent_im_capabilities_default_off_and_update(store_db):
    agent_store.create_agent("agent-a", "Prompt.", ["shell"])

    created = agent_store.get_by_name("agent-a")
    assert created is not None
    assert created.supports_dm is False
    assert created.supports_groups is False

    agent_store.set_im_capabilities("agent-a", supports_dm=True, supports_groups=True)

    updated = agent_store.get_by_name("agent-a")
    assert updated is not None
    assert updated.supports_dm is True
    assert updated.supports_groups is True
