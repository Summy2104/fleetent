"""Unit tests for fleetent.auth: password hashing, sessions, roles, admin seed."""

from typing import Any

import pytest

from fleetent import auth, user_store


@pytest.fixture(autouse=True)
def _clear_sessions() -> Any:
    auth._SESSIONS.clear()
    yield
    auth._SESSIONS.clear()


def _user(**overrides: Any) -> user_store.User:
    base: dict[str, Any] = {
        "id": "u1",
        "name": "alice",
        "api_key": "ma-x",
        "created_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return user_store.User(**base)


# --- password hashing -------------------------------------------------------


def test_hash_password_roundtrip_verifies() -> None:
    stored = auth.hash_password("hunter2")
    assert stored.startswith("scrypt$")
    assert auth.verify_password("hunter2", stored) is True


def test_hash_password_uses_random_salt() -> None:
    assert auth.hash_password("same") != auth.hash_password("same")


def test_verify_password_wrong_password() -> None:
    stored = auth.hash_password("correct")
    assert auth.verify_password("wrong", stored) is False


def test_verify_password_none_or_empty_stored() -> None:
    assert auth.verify_password("anything", None) is False
    assert auth.verify_password("anything", "") is False


def test_verify_password_malformed_stored_returns_false() -> None:
    assert auth.verify_password("x", "not-a-valid-format") is False


def test_verify_password_unknown_algo_returns_false() -> None:
    assert auth.verify_password("x", "bcrypt$aa$bb") is False


# --- session lifecycle ------------------------------------------------------


def test_create_session_returns_token_and_registers_user() -> None:
    token = auth.create_session("u42")
    assert auth.validate_session(token, idle_timeout=1000) == "u42"


def test_validate_session_unknown_token_returns_none() -> None:
    assert auth.validate_session("nope", idle_timeout=1000) is None


def test_validate_session_idle_expired_removes_session(monkeypatch: Any) -> None:
    clock = {"t": 100.0}
    monkeypatch.setattr(auth, "_clock", lambda: clock["t"])
    token = auth.create_session("u1")
    clock["t"] = 100.0 + 50.0  # advance past idle_timeout
    assert auth.validate_session(token, idle_timeout=10) is None
    # Session was evicted, so a second validate also returns None.
    assert auth.validate_session(token, idle_timeout=10) is None


def test_validate_session_refreshes_last_active(monkeypatch: Any) -> None:
    clock = {"t": 100.0}
    monkeypatch.setattr(auth, "_clock", lambda: clock["t"])
    token = auth.create_session("u1")
    clock["t"] = 105.0
    assert auth.validate_session(token, idle_timeout=10) == "u1"
    # last_active refreshed to 105; advancing to 113 is still within 10s.
    clock["t"] = 113.0
    assert auth.validate_session(token, idle_timeout=10) == "u1"


def test_logout_invalidates_session() -> None:
    token = auth.create_session("u1")
    auth.logout(token)
    assert auth.validate_session(token, idle_timeout=1000) is None


def test_logout_unknown_token_is_noop() -> None:
    auth.logout("does-not-exist")  # must not raise


# --- roles ------------------------------------------------------------------


def test_has_role_true_when_in_allowed() -> None:
    assert auth.has_role(_user(role="admin"), {"admin", "owner"}) is True


def test_has_role_false_when_not_allowed() -> None:
    assert auth.has_role(_user(role="viewer"), {"admin"}) is False


def test_has_role_false_for_none_user() -> None:
    assert auth.has_role(None, {"admin"}) is False


def test_require_role_passes_for_allowed() -> None:
    auth.require_role(_user(role="admin"), {"admin"})  # no raise


def test_require_role_raises_for_disallowed() -> None:
    with pytest.raises(PermissionError):
        auth.require_role(_user(role="viewer"), {"admin"})


# --- built-in admin seed ----------------------------------------------------


def test_seed_builtin_admin_creates_when_absent(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}
    created = _user(id="admin-id", name=auth.BUILTIN_ADMIN_NAME)

    monkeypatch.setattr(user_store, "get_builtin_admin", lambda: None)
    monkeypatch.setattr(user_store, "create_user", lambda name, email: created)
    monkeypatch.setattr(
        user_store, "set_role", lambda uid, role: calls.update({"role": (uid, role)})
    )
    monkeypatch.setattr(
        user_store,
        "set_password",
        lambda uid, ph, must_reset: calls.update({"pw": (uid, must_reset)}),
    )
    monkeypatch.setattr(user_store, "get_by_id", lambda uid: created)

    result = auth.seed_builtin_admin()
    assert result is not None
    user, temp_password = result
    assert user is created
    assert temp_password == auth.BUILTIN_ADMIN_PASSWORD
    assert calls["role"] == ("admin-id", "built_in_admin")
    assert calls["pw"][1] is True  # forced reset


def test_seed_builtin_admin_noop_when_reset_already_required(monkeypatch: Any) -> None:
    existing = _user(id="admin-id", must_reset=1)
    set_reset_called = {"n": 0}
    monkeypatch.setattr(user_store, "get_builtin_admin", lambda: existing)
    monkeypatch.setattr(
        user_store,
        "set_must_reset",
        lambda uid, flag: set_reset_called.update({"n": set_reset_called["n"] + 1}),
    )
    assert auth.seed_builtin_admin() is None
    assert set_reset_called["n"] == 0


def test_seed_builtin_admin_reasserts_reset_on_default_password(monkeypatch: Any) -> None:
    default_hash = auth.hash_password(auth.BUILTIN_ADMIN_PASSWORD)
    existing = _user(id="admin-id", must_reset=0, password_hash=default_hash)
    reasserted: dict[str, Any] = {}
    monkeypatch.setattr(user_store, "get_builtin_admin", lambda: existing)
    monkeypatch.setattr(
        user_store, "set_must_reset", lambda uid, flag: reasserted.update({uid: flag})
    )
    assert auth.seed_builtin_admin() is None
    assert reasserted == {"admin-id": True}
