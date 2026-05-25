import pytest

from fleetent import user_store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")


def test_create_user_returns_user():
    user = user_store.create_user("Alice")
    assert user.name == "Alice"
    assert user.api_key.startswith("ma-")
    assert len(user.id) == 36  # uuid4


def test_get_by_api_key_found():
    user = user_store.create_user("Bob")
    found = user_store.get_by_api_key(user.api_key)
    assert found is not None
    assert found.id == user.id


def test_get_by_api_key_not_found():
    assert user_store.get_by_api_key("ma-doesnotexist") is None


def test_get_by_id_found():
    user = user_store.create_user("Carol")
    found = user_store.get_by_id(user.id)
    assert found is not None
    assert found.name == "Carol"


def test_get_by_id_not_found():
    assert user_store.get_by_id("00000000-0000-0000-0000-000000000000") is None


def test_list_users_returns_all():
    user_store.create_user("Dave")
    user_store.create_user("Eve")
    users = user_store.list_users()
    names = [u.name for u in users]
    assert "Dave" in names and "Eve" in names


def test_rotate_key_changes_api_key():
    user = user_store.create_user("Frank")
    old_key = user.api_key
    updated = user_store.rotate_key(user.id)
    assert updated.api_key != old_key
    assert updated.api_key.startswith("ma-")
    assert user_store.get_by_api_key(old_key) is None
    assert user_store.get_by_api_key(updated.api_key) is not None
