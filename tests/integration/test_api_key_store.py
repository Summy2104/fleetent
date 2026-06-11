import datetime

import pytest

import fleetent.platform.user_management.api_key_store as aks
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    return tmp_path / "users.db"


def _columns(db_path):
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(api_keys)").fetchall()}


def test_table_columns(db):
    assert {
        "id",
        "user_id",
        "key_hash",
        "prefix",
        "scope",
        "note",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_used_at",
        "last_ip",
        "last_ua",
        "call_count",
    } <= _columns(db)


def test_issue_returns_plaintext_once_and_stores_hash(db):
    plaintext, meta = aks.issue_key("u1", scope=["*"], note="ci")
    assert plaintext.startswith("ma-")
    # stored value is not the plaintext
    rows = aks.list_keys("u1")
    assert len(rows) == 1
    assert "key_hash" not in rows[0] or rows[0].get("key_hash") != plaintext
    assert rows[0]["prefix"] and rows[0]["prefix"] in plaintext
    # resolve finds it by plaintext
    resolved = aks.resolve(plaintext)
    assert resolved is not None and resolved["user_id"] == "u1"


def test_list_keys_hides_plaintext(db):
    plaintext, _ = aks.issue_key("u1")
    row = aks.list_keys("u1")[0]
    assert plaintext not in str(row)


def test_independent_revoke(db):
    p_a, meta_a = aks.issue_key("u1", note="A")
    p_b, _ = aks.issue_key("u1", note="B")
    aks.revoke_key(meta_a["id"])
    assert aks.resolve(p_a) is None
    assert aks.resolve(p_b) is not None


def test_expired_key_not_resolved(db):
    past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
    plaintext, _ = aks.issue_key("u1", expires_at=past)
    assert aks.resolve(plaintext) is None


def test_record_usage_updates_fields(db):
    plaintext, meta = aks.issue_key("u1")
    aks.record_usage(meta["id"], ip="1.2.3.4", ua="curl/8")
    row = next(r for r in aks.list_keys("u1") if r["id"] == meta["id"])
    assert row["last_ip"] == "1.2.3.4"
    assert row["last_ua"] == "curl/8"
    assert row["call_count"] == 1


def test_check_scope(db):
    assert aks.check_scope(["*"], "anything") is True
    assert aks.check_scope(["ops-bot"], "ops-bot") is True
    assert aks.check_scope(["ops-bot"], "support-bot") is False


def test_rotate_key(db):
    p_old, meta = aks.issue_key("u1", scope=["ops-bot"], note="ci")
    p_new, new_meta = aks.rotate_key(meta["id"])
    assert aks.resolve(p_old) is None
    resolved = aks.resolve(p_new)
    assert resolved is not None and resolved["user_id"] == "u1"
    assert resolved["scope"] == ["ops-bot"]
