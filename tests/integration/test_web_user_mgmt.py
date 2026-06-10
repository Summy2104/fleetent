import pytest

import fleetent.auth as auth
import fleetent.platform.user_management.api_key_store as aks
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    for mod in (user_store, aks):
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
    user_store._init_db()
    return tmp_path / "users.db"


def test_create_web_user(db):
    u = user_store.create_web_user("a@x.com", "Alice", password_hash=auth.hash_password("pw"))
    assert u.email == "a@x.com"
    assert user_store.get_by_email("a@x.com").id == u.id


def test_duplicate_email_rejected(db):
    user_store.create_web_user("a@x.com", "Alice")
    with pytest.raises(ValueError):
        user_store.create_web_user("a@x.com", "Other")


def test_disable_and_delete_user(db):
    u = user_store.create_web_user("b@x.com", "Bob")
    user_store.disable_user(u.id)
    assert user_store.get_by_id(u.id).status == "disabled"
    user_store.delete_user(u.id)
    assert user_store.get_by_id(u.id) is None


def test_builtin_admin_protected_from_disable_delete(db):
    admin, _ = auth.seed_builtin_admin()
    with pytest.raises(PermissionError):
        user_store.disable_user(admin.id)
    with pytest.raises(PermissionError):
        user_store.delete_user(admin.id)


def test_bulk_import(db):
    user_store.create_web_user("dup@x.com", "Existing")
    result = user_store.bulk_import_users(
        [{"email": "n1@x.com", "name": "N1"}, {"email": "dup@x.com", "name": "Dup"}]
    )
    assert len(result["created"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["email"] == "dup@x.com"


def test_no_self_registration_symbol(db):
    # There is no public registration entry point in user_store.
    assert not hasattr(user_store, "self_register")
