from pathlib import Path

import pytest

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.governance.blocklist as blocklist
import fleetent.platform.user_management.api_key_store as aks
import fleetent.platform.user_management.block_service as block_service
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    return tmp_path / "users.db"


def test_block_user_cascade(db):
    u = user_store.create_web_user("a@x.com", "Alice")
    plaintext, _ = aks.issue_key(u.id)
    im_user_store.get_or_create("slack", "U1", "default")  # creates User; bind not needed
    # bind the IM identity to the blocked user for the cascade test
    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE im_users SET user_id = ? WHERE platform='slack'", (u.id,))

    block_service.block_user(u.id, reason="abuse", actor="admin1")

    assert user_store.get_by_id(u.id).status == "blocked"
    assert aks.resolve(plaintext) is None  # key revoked
    assert blocklist.is_registration_blocked("a@x.com") is True
    with sqlite3.connect(db) as conn:
        mapped = conn.execute(
            "SELECT COUNT(*) FROM im_users WHERE user_id = ?", (u.id,)
        ).fetchone()[0]
    assert mapped == 1
    assert len(audit.search_audit(action="block_user", target_id=u.id)) == 1


def test_blocked_key_rejected_via_authenticate(db):
    u = user_store.create_web_user("b@x.com", "Bob")
    plaintext, _ = aks.issue_key(u.id)
    block_service.block_user(u.id, reason="x")
    assert user_store.authenticate(plaintext) is None


def test_blocked_email_cannot_reregister(db):
    u = user_store.create_web_user("c@x.com", "Cara")
    block_service.block_user(u.id, reason="x")
    with pytest.raises(PermissionError):
        user_store.create_web_user("c@x.com", "Cara2")


def test_unblock_does_not_revive_keys(db):
    u = user_store.create_web_user("d@x.com", "Dan")
    plaintext, _ = aks.issue_key(u.id)
    block_service.block_user(u.id, reason="x")
    block_service.unblock_user(u.id, actor="admin1")
    assert user_store.get_by_id(u.id).status == "active"
    assert aks.resolve(plaintext) is None  # still revoked


def test_batch_block_shared_id(db):
    u1 = user_store.create_web_user("e@x.com", "E")
    u2 = user_store.create_web_user("f@x.com", "F")
    batch_id = block_service.batch_block([u1.id, u2.id], reason="raid", actor="admin1")
    rows = [r for r in audit.search_audit(action="block_user") if r["batch_id"] == batch_id]
    assert len(rows) == 2


def test_builtin_admin_cannot_be_blocked(db):
    admin, _ = auth.seed_builtin_admin()
    with pytest.raises(PermissionError):
        block_service.block_user(admin.id, reason="x")


def test_ban_registration_marks_email_blocked(db):
    assert blocklist.is_registration_blocked("z@x.com") is False

    blocklist.ban_registration("z@x.com", reason="ops", batch_id="batch-z")

    assert blocklist.is_registration_blocked("z@x.com") is True


def test_blocklist_store_is_crud_only_and_uses_db_boundary():
    source = Path("src/fleetent/governance/blocklist.py").read_text()

    assert "CREATE TABLE" not in source
    assert "DB_PATH as DB_PATH" not in source
    assert "?" not in source
    assert ":email" in source
