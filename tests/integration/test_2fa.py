import pytest

import fleetent.auth as auth
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    user_store._init_db()
    return tmp_path / "users.db"


def test_totp_roundtrip_fixed_time():
    secret = auth.generate_totp_secret()
    code = auth.totp(secret, t=1_000_000)
    assert len(code) == 6 and code.isdigit()
    assert auth.verify_totp(secret, code, t=1_000_000) is True


def test_totp_wrong_code_rejected():
    secret = auth.generate_totp_secret()
    assert (
        auth.verify_totp(secret, "000000", t=1_000_000) is False
        or auth.totp(secret, t=1_000_000) == "000000"
    )


def test_totp_window_tolerance():
    secret = auth.generate_totp_secret()
    code = auth.totp(secret, t=1_000_000)
    # code from previous step still accepted within window
    assert auth.verify_totp(secret, code, t=1_000_000 + 30, window=1) is True


def test_enable_and_verify_user_2fa(db):
    u = user_store.create_user("Alice")
    secret = auth.enable_2fa(u.id)
    assert user_store.get_by_id(u.id).totp_secret == secret
    code = auth.totp(secret, t=1_000_000)
    assert auth.verify_user_2fa(u.id, code, t=1_000_000) is True
    assert (
        auth.verify_user_2fa(u.id, "999999", t=1_000_000) is False
        or auth.totp(secret, t=1_000_000) == "999999"
    )


def test_user_without_2fa_fails_verify(db):
    u = user_store.create_user("Bob")
    assert auth.verify_user_2fa(u.id, "123456") is False
