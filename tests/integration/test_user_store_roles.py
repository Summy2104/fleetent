import pytest

import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _columns(db_path):
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}


def test_users_table_has_new_columns(db):
    assert {"email", "password_hash", "role", "status", "must_reset"} <= _columns(db)


def test_defaults_role_viewer_status_active(db):
    u, _ = user_store.create_user("Alice")
    fetched = user_store.get_by_id(u.id)
    assert fetched.role == "viewer"
    assert fetched.status == "active"
    assert fetched.must_reset == 0


def test_set_role_and_status(db):
    u, _ = user_store.create_user("Bob")
    user_store.set_role(u.id, "admin")
    user_store.set_status(u.id, "disabled")
    fetched = user_store.get_by_id(u.id)
    assert fetched.role == "admin"
    assert fetched.status == "disabled"


def test_set_password_and_must_reset(db):
    u, _ = user_store.create_user("Cara")
    user_store.set_password(u.id, "hash:abc", must_reset=True)
    fetched = user_store.get_by_id(u.id)
    assert fetched.password_hash == "hash:abc"
    assert fetched.must_reset == 1
    user_store.set_must_reset(u.id, False)
    assert user_store.get_by_id(u.id).must_reset == 0


def test_get_by_email(db):
    u, _ = user_store.create_user("Dan", email="dan@example.com")
    found = user_store.get_by_email("dan@example.com")
    assert found is not None and found.id == u.id
    assert user_store.get_by_email("nobody@example.com") is None


def test_idempotent_init_preserves_rows(db):
    u, _ = user_store.create_user("Eve")
    user_store._init_db()  # run again — should not drop or error
    assert user_store.get_by_id(u.id) is not None
