import pytest

import fleetent.governance.audit_log as audit
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "users.db")
    audit._init_db()
    return tmp_path / "users.db"


def test_table_columns(db):
    import sqlite3

    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    assert {
        "id",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "detail",
        "batch_id",
        "created_at",
    } <= cols


def test_write_and_search_by_action(db):
    audit.write_audit("admin1", "rotate_key", target_type="user", target_id="u1")
    audit.write_audit("admin1", "block_user", target_type="user", target_id="u2")
    rows = audit.search_audit(action="rotate_key")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == "admin1"
    assert rows[0]["target_id"] == "u1"


def test_search_by_actor_and_target(db):
    audit.write_audit("admin1", "block_user", target_type="user", target_id="u2")
    audit.write_audit("admin2", "block_user", target_type="user", target_id="u3")
    assert len(audit.search_audit(actor="admin2")) == 1
    assert len(audit.search_audit(target_id="u2")) == 1


def test_detail_roundtrip(db):
    audit.write_audit("admin1", "change_quota", detail={"token_limit": 10000})
    row = audit.search_audit(action="change_quota")[0]
    assert row["detail"] == {"token_limit": 10000}


def test_batch_id_shared(db):
    audit.write_audit("admin1", "block_user", target_id="u1", batch_id="b-1")
    audit.write_audit("admin1", "block_user", target_id="u2", batch_id="b-1")
    rows = [r for r in audit.search_audit(action="block_user") if r["batch_id"] == "b-1"]
    assert len(rows) == 2
