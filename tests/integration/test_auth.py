import pytest

import fleetent.auth as auth
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    return tmp_path / "users.db"


def test_password_hash_roundtrip(db):
    h = auth.hash_password("s3cret")
    assert h != "s3cret"
    assert auth.verify_password("s3cret", h) is True
    assert auth.verify_password("wrong", h) is False


def test_seed_builtin_admin(db):
    result = auth.seed_builtin_admin()
    assert result is not None
    user, temp_password = result
    assert user.role == "admin"
    # fixed default credentials admin/admin; first login forces a password change
    assert user.name == auth.BUILTIN_ADMIN_NAME == "admin"
    assert temp_password == auth.BUILTIN_ADMIN_PASSWORD == "admin"
    assert user.must_reset == 1
    assert auth.verify_password(temp_password, user_store.get_by_id(user.id).password_hash)
    # second seed is a no-op
    assert auth.seed_builtin_admin() is None


def test_seed_builtin_admin_is_noop_when_active_admin_exists(db):
    admin = user_store.create_web_user(
        "owner@example.com", "Owner", password_hash=auth.hash_password("pw"), role="admin"
    )

    assert auth.seed_builtin_admin() is None
    users = user_store.list_users()
    assert [user.id for user in users] == [admin.id]


def test_seed_builtin_admin_recreates_bootstrap_when_no_active_admin_exists(db):
    admin = user_store.create_web_user(
        "owner@example.com", "Owner", password_hash=auth.hash_password("pw"), role="admin"
    )
    with user_store._db().transaction() as conn:
        conn.execute(
            "UPDATE users SET status = :status WHERE id = :id",
            {"status": "blocked", "id": admin.id},
        )

    result = auth.seed_builtin_admin()

    assert result is not None
    user, temp_password = result
    assert user.name == auth.BUILTIN_ADMIN_NAME
    assert user.email is None
    assert user.role == "admin"
    assert user.must_reset == 1
    assert temp_password == auth.BUILTIN_ADMIN_PASSWORD
    assert auth.verify_password(temp_password, user_store.get_by_id(user.id).password_hash)


def test_seed_reasserts_must_reset_while_default_password(db):
    # Insecure default admin/admin must stay gated: if must_reset got cleared but the
    # password is still the bootstrap default, a later seed re-forces the reset.
    user, _ = auth.seed_builtin_admin()
    user_store.set_password(
        user.id, auth.hash_password(auth.BUILTIN_ADMIN_PASSWORD), must_reset=False
    )
    assert user_store.get_by_id(user.id).must_reset == 0
    assert auth.seed_builtin_admin() is None  # still a no-op return
    assert user_store.get_by_id(user.id).must_reset == 1  # gate re-asserted


def test_seed_leaves_must_reset_when_password_changed(db):
    # If the admin set a real password, do not nag for another reset.
    user, _ = auth.seed_builtin_admin()
    user_store.set_password(user.id, auth.hash_password("a-real-password"), must_reset=False)
    assert auth.seed_builtin_admin() is None
    assert user_store.get_by_id(user.id).must_reset == 0


def test_builtin_admin_cannot_be_demoted(db):
    user, _ = auth.seed_builtin_admin()
    with pytest.raises(PermissionError):
        user_store.set_role(user.id, "viewer")
    assert user_store.get_by_id(user.id).role == "admin"


def test_login_session_create_and_validate(db):
    u, _ = user_store.create_user("Alice")
    token = auth.create_session(u.id)
    assert auth.validate_session(token, idle_timeout=300) == u.id
    auth.logout(token)
    assert auth.validate_session(token, idle_timeout=300) is None


def test_session_idle_timeout(db, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(auth, "_clock", lambda: clock["t"])
    u, _ = user_store.create_user("Bob")
    token = auth.create_session(u.id)
    clock["t"] = 1000.0 + 301  # exceed idle timeout
    assert auth.validate_session(token, idle_timeout=300) is None


def test_has_role_and_require_role(db):
    u, _ = user_store.create_user("Cara")
    user_store.set_role(u.id, "viewer")
    viewer = user_store.get_by_id(u.id)
    assert auth.has_role(viewer, {"admin"}) is False
    with pytest.raises(PermissionError):
        auth.require_role(viewer, {"admin"})
    user_store.set_role(u.id, "admin")
    admin = user_store.get_by_id(u.id)
    assert auth.has_role(admin, {"admin"}) is True
    auth.require_role(admin, {"admin"})  # no raise
