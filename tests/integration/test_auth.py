import pytest

import fleetent.auth as auth
import fleetent.platform.user_management.api_key_store as aks
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(aks, "DB_PATH", tmp_path / "users.db")
    user_store._init_db()
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
    assert user.role == "built_in_admin"
    # fixed default credentials admin/admin; no forced reset
    assert user.name == auth.BUILTIN_ADMIN_NAME == "admin"
    assert temp_password == auth.BUILTIN_ADMIN_PASSWORD == "admin"
    assert user.must_reset == 0
    assert auth.verify_password(temp_password, user_store.get_by_id(user.id).password_hash)
    # second seed is a no-op
    assert auth.seed_builtin_admin() is None


def test_builtin_admin_cannot_be_demoted(db):
    user, _ = auth.seed_builtin_admin()
    with pytest.raises(PermissionError):
        user_store.set_role(user.id, "viewer")
    # still built_in_admin
    assert user_store.get_by_id(user.id).role == "built_in_admin"


def test_login_session_create_and_validate(db):
    u = user_store.create_user("Alice")
    token = auth.create_session(u.id)
    assert auth.validate_session(token, idle_timeout=300) == u.id
    auth.logout(token)
    assert auth.validate_session(token, idle_timeout=300) is None


def test_session_idle_timeout(db, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(auth, "_clock", lambda: clock["t"])
    u = user_store.create_user("Bob")
    token = auth.create_session(u.id)
    clock["t"] = 1000.0 + 301  # exceed idle timeout
    assert auth.validate_session(token, idle_timeout=300) is None


def test_has_role_and_require_role(db):
    u = user_store.create_user("Cara")
    user_store.set_role(u.id, "viewer")
    viewer = user_store.get_by_id(u.id)
    assert auth.has_role(viewer, {"admin", "built_in_admin"}) is False
    with pytest.raises(PermissionError):
        auth.require_role(viewer, {"admin", "built_in_admin"})
    user_store.set_role(u.id, "admin")
    admin = user_store.get_by_id(u.id)
    assert auth.has_role(admin, {"admin", "built_in_admin"}) is True
    auth.require_role(admin, {"admin", "built_in_admin"})  # no raise
