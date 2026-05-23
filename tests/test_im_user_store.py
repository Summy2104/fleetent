import sqlite3

import pytest

import mini_agent.im_user_store as im_user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(im_user_store, "DB_PATH", db_path)
    # Also need to monkeypatch user_store DB_PATH since im_user_store creates users too
    import mini_agent.user_store as user_store
    monkeypatch.setattr(user_store, "DB_PATH", db_path)
    im_user_store._init_db()
    return db_path


def test_get_or_create_new_user(db):
    user = im_user_store.get_or_create("slack", "U123")
    assert user.id is not None
    assert user.name == "slack:U123"


def test_get_or_create_returns_same_user(db):
    user1 = im_user_store.get_or_create("slack", "U123")
    user2 = im_user_store.get_or_create("slack", "U123")
    assert user1.id == user2.id


def test_different_platforms_different_users(db):
    slack_user = im_user_store.get_or_create("slack", "U123")
    tg_user = im_user_store.get_or_create("telegram", "U123")
    assert slack_user.id != tg_user.id


def test_unique_constraint(db):
    im_user_store.get_or_create("slack", "U123")
    im_user_store.get_or_create("slack", "U123")  # should not raise
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM im_users WHERE platform='slack' AND platform_user_id='U123'"
    ).fetchone()[0]
    conn.close()
    assert count == 1
