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


# --- allowlist tests ---

def test_get_or_create_new_user_is_not_allowed(db):
    user = im_user_store.get_or_create("slack", "U999")
    assert im_user_store.check_allowed_by_user_id(user.id) is False


def test_check_allowed_returns_true_for_unknown_user(db):
    assert im_user_store.check_allowed_by_user_id("not-an-im-user") is True


def test_approve_user_sets_allowed_true(db):
    user = im_user_store.get_or_create("slack", "UA1")
    pending = im_user_store.list_pending()
    im_user_store.approve_user(pending[0]["id"])
    assert im_user_store.check_allowed_by_user_id(user.id) is True


def test_block_user_revokes_access(db):
    user = im_user_store.get_or_create("slack", "UB1")
    pending = im_user_store.list_pending()
    im_user_store.approve_user(pending[0]["id"])
    assert im_user_store.check_allowed_by_user_id(user.id) is True
    im_user_store.block_user(pending[0]["id"])
    assert im_user_store.check_allowed_by_user_id(user.id) is False


def test_block_user_idempotent(db):
    im_user_store.get_or_create("slack", "UC1")
    pending = im_user_store.list_pending()
    im_user_id = pending[0]["id"]
    im_user_store.block_user(im_user_id)
    im_user_store.block_user(im_user_id)  # should not raise


def test_list_pending_returns_only_unapproved(db):
    im_user_store.get_or_create("slack", "UD1")
    im_user_store.get_or_create("slack", "UD2")
    pending = im_user_store.list_pending()
    assert len(pending) == 2
    im_user_store.approve_user(pending[0]["id"])
    remaining = im_user_store.list_pending()
    assert len(remaining) == 1
    assert remaining[0]["platform_user_id"] == "UD2"


def test_list_pending_empty(db):
    assert im_user_store.list_pending() == []
