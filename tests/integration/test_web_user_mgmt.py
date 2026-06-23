import pytest

import fleetent.auth as auth
import fleetent.user_store as user_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    return tmp_path / "users.db"


def test_create_web_user(db):
    u = user_store.create_web_user("a@x.com", "Alice", password_hash=auth.hash_password("pw"))
    assert u.email == "a@x.com"
    assert user_store.get_by_email("default", "a@x.com").id == u.id


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


def test_delete_user_rejects_tenant_or_team_approver(db):
    tenant_approver, _ = user_store.create_user("Tenant Approver")
    team_approver, _ = user_store.create_user("Team Approver")
    safe_user, _ = user_store.create_user("Safe Delete")
    tenancy_store.create_team(id="support", tenant_id="default", name="Support")
    tenancy_store.set_tenant_approver("default", tenant_approver.id)
    tenancy_store.set_team_approver("support", team_approver.id)

    with pytest.raises(PermissionError, match="tenant approver for tenant 'default'"):
        user_store.delete_user(tenant_approver.id)
    with pytest.raises(PermissionError, match="team approver for team 'support'"):
        user_store.delete_user(team_approver.id)

    user_store.delete_user(safe_user.id)
    assert user_store.get_by_id(safe_user.id) is None


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
