import pytest

import fleetent.audit_log as audit
import fleetent.im_user_store as im_user_store
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    for mod in (user_store, im_user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "users.db")
    user_store._init_db()
    im_user_store._init_db()
    audit._init_db()
    return tmp_path / "users.db"


def test_block_and_restore_audited(db):
    user = im_user_store.get_or_create("slack", "U1")
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    im_user_store.block_im_user(im_id, reason="spam", actor="admin1")
    assert im_user_store.check_allowed_by_user_id(user.id) is False
    assert len(audit.search_audit(action="block_im_user", target_id=str(im_id))) == 1
    im_user_store.restore_im_user(im_id, reason="appealed", actor="admin1")
    assert im_user_store.check_allowed_by_user_id(user.id) is True
    assert len(audit.search_audit(action="restore_im_user", target_id=str(im_id))) == 1


def test_batch_block_shared_id(db):
    u1 = im_user_store.get_or_create("slack", "A1")
    u2 = im_user_store.get_or_create("telegram", "B1")
    id1 = im_user_store.list_im_identities(u1.id)[0]["id"]
    id2 = im_user_store.list_im_identities(u2.id)[0]["id"]
    batch_id = im_user_store.batch_block_im([id1, id2], reason="raid", actor="admin1")
    rows = [r for r in audit.search_audit(action="block_im_user") if r["batch_id"] == batch_id]
    assert len(rows) == 2


def test_list_identities_merges_platforms(db):
    # Same internal user bound to two platforms (simulate by reusing user_id).
    u = im_user_store.get_or_create("slack", "M1")
    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO im_users (platform, platform_user_id, user_id, allowed, created_at)"
            " VALUES ('telegram','M2',?,1,'2026-01-01')",
            (u.id,),
        )
    identities = im_user_store.list_im_identities(u.id)
    platforms = {i["platform"] for i in identities}
    assert platforms == {"slack", "telegram"}
