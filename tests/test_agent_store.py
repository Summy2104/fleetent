import pytest

import fleetent.agent_store as agent_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_store, "DB_PATH", tmp_path / "users.db")
    import fleetent.user_store as user_store
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    agent_store._init_db()
    return tmp_path / "users.db"


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
