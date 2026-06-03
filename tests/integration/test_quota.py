import pytest

import fleetent.governance.quota as quota
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(quota, "DB_PATH", tmp_path / "users.db")
    quota._init_db()
    return tmp_path / "users.db"


def test_no_quota_allows(db):
    assert quota.check_quota("u1", tokens=1000) is True


def test_per_user_token_limit(db):
    quota.set_quota("user:u1", token_limit=10000)
    quota.record_usage("u1", tokens=9000)
    assert quota.check_quota("u1", tokens=500) is True
    quota.record_usage("u1", tokens=1500)  # now 10500 used
    assert quota.check_quota("u1", tokens=1) is False


def test_per_user_call_limit(db):
    quota.set_quota("user:u1", call_limit=2)
    quota.record_usage("u1", tokens=1)
    quota.record_usage("u1", tokens=1)
    assert quota.check_quota("u1", tokens=1) is False


def test_global_quota_applies_to_all(db):
    quota.set_quota("global", token_limit=100)
    quota.record_usage("u1", tokens=60)
    quota.record_usage("u2", tokens=50)  # global now 110
    assert quota.check_quota("u3", tokens=1) is False


def test_within_quota_proceeds(db):
    quota.set_quota("user:u1", token_limit=100)
    quota.record_usage("u1", tokens=50)
    assert quota.check_quota("u1", tokens=10) is True


def test_system_internal_call_exempt(db):
    quota.set_quota("global", call_limit=0)  # everything blocked for regular users
    assert quota.check_quota("u1") is False
    assert quota.check_quota(quota.SYSTEM_USER_ID) is True  # internal calls exempt


def test_system_usage_not_recorded(db):
    quota.set_quota("global", call_limit=5)
    quota.record_usage(quota.SYSTEM_USER_ID, tokens=1000)  # no-op for system
    assert quota._get_usage("global") == (0, 0)
