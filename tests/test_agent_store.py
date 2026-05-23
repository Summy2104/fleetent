import pytest

import mini_agent.agent_store as agent_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_store, "DB_PATH", tmp_path / "users.db")
    import mini_agent.user_store as user_store
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
