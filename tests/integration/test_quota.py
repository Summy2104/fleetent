import pytest

import fleetent.quota as quota
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
