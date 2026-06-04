import sqlite3

import pytest

from fleetent.platform.im_gateway_management import identity as im_user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(im_user_store, "DB_PATH", db_path)
    # Also need to monkeypatch user_store DB_PATH since im_user_store creates users too
    import fleetent.user_store as user_store

    monkeypatch.setattr(user_store, "DB_PATH", db_path)
    im_user_store._init_db()
    return db_path


_OWNER = "owner1"


def test_get_or_create_new_user(db):
    user = im_user_store.get_or_create(_OWNER, "slack", "U123")
    assert user.id is not None
    assert user.name == "slack:U123"


def test_get_or_create_returns_same_user(db):
    user1 = im_user_store.get_or_create(_OWNER, "slack", "U123")
    user2 = im_user_store.get_or_create(_OWNER, "slack", "U123")
    assert user1.id == user2.id


def test_different_platforms_different_users(db):
    slack_user = im_user_store.get_or_create(_OWNER, "slack", "U123")
    tg_user = im_user_store.get_or_create(_OWNER, "telegram", "U123")
    assert slack_user.id != tg_user.id


def test_rebind_im_identity_to_existing_user(db):
    import fleetent.user_store as user_store

    # slack:U1 starts bound to its own auto-created user; telegram:T1 to another.
    slack_user = im_user_store.get_or_create(_OWNER, "slack", "U1")
    target = im_user_store.get_or_create(_OWNER, "telegram", "T1")
    im_id = im_user_store.list_im_identities(slack_user.id)[0]["id"]

    im_user_store.rebind_im_identity(im_id, target.id)

    # slack:U1 now belongs to target → many-to-one (target has both identities).
    assert im_user_store.list_im_identities(slack_user.id) == []
    platforms = {i["platform"] for i in im_user_store.list_im_identities(target.id)}
    assert platforms == {"slack", "telegram"}
    # orphan kept (decision): old auto-user still exists
    assert user_store.get_by_id(slack_user.id) is not None


def test_rebind_unknown_target_raises(db):
    u = im_user_store.get_or_create(_OWNER, "slack", "U2")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    with pytest.raises(ValueError):
        im_user_store.rebind_im_identity(im_id, "ghost-user-id")


def test_rebind_unknown_identity_raises(db):
    target = im_user_store.get_or_create(_OWNER, "slack", "U3")
    with pytest.raises(ValueError):
        im_user_store.rebind_im_identity(999999, target.id)


def test_unique_constraint(db):
    im_user_store.get_or_create(_OWNER, "slack", "U123")
    im_user_store.get_or_create(_OWNER, "slack", "U123")  # should not raise
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM im_users WHERE platform='slack' AND platform_user_id='U123'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


# --- allowlist tests (v1.0: default-allow) ---


def test_get_or_create_new_user_is_allowed_by_default(db):
    user = im_user_store.get_or_create(_OWNER, "slack", "U999")
    assert im_user_store.check_allowed_by_user_id(user.id) is True


def test_check_allowed_returns_true_for_unknown_user(db):
    assert im_user_store.check_allowed_by_user_id("not-an-im-user") is True


def test_new_users_not_pending(db):
    # Default-allow: newly created users are not pending approval.
    im_user_store.get_or_create(_OWNER, "slack", "UD1")
    im_user_store.get_or_create(_OWNER, "slack", "UD2")
    assert im_user_store.list_pending() == []


def test_legacy_block_user_revokes_access(db):
    user = im_user_store.get_or_create(_OWNER, "slack", "UB1")
    assert im_user_store.check_allowed_by_user_id(user.id) is True
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    im_user_store.block_user(im_id)  # legacy CLI-style block still sets allowed=0
    assert im_user_store.check_allowed_by_user_id(user.id) is False


def test_list_pending_empty(db):
    assert im_user_store.list_pending() == []
