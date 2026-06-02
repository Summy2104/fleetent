import pytest

import fleetent.platform.im_gateway_management.im_connector_store as ics
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ics, "DB_PATH", tmp_path / "users.db")
    ics._init_db()
    return tmp_path / "users.db"


def _columns(db_path):
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(im_connectors)").fetchall()}


def test_table_has_expected_columns(db):
    cols = _columns(db)
    assert {
        "id",
        "platform",
        "enabled",
        "allowlist_enforced",
        "config",
        "status",
        "last_heartbeat_at",
        "last_error",
        "created_at",
        "updated_at",
    } <= cols


def test_platform_is_unique(db):
    ics.upsert_connector("slack")
    ics.upsert_connector("slack")  # upsert, not a second row
    rows = ics.list_connectors()
    assert [r["platform"] for r in rows].count("slack") == 1


def test_report_status_updates_status(db):
    ics.upsert_connector("slack")
    ics.report_status("slack", "connected")
    assert ics.get_connector("slack")["status"] == "connected"


def test_report_status_with_error_sets_last_error(db):
    ics.report_status("telegram", "error", error="network timeout")
    row = ics.get_connector("telegram")
    assert row["status"] == "error"
    assert row["last_error"] == "network timeout"


def test_heartbeat_sets_timestamp_without_changing_status(db):
    ics.report_status("slack", "connected")
    ics.heartbeat("slack")
    row = ics.get_connector("slack")
    assert row["last_heartbeat_at"] is not None
    assert row["status"] == "connected"


def test_set_enabled_and_allowlist_enforced(db):
    ics.upsert_connector("slack")
    ics.set_enabled("slack", True)
    ics.set_allowlist_enforced("slack", True)
    row = ics.get_connector("slack")
    assert row["enabled"] == 1
    assert row["allowlist_enforced"] == 1
    ics.set_enabled("slack", False)
    assert ics.get_connector("slack")["enabled"] == 0


def test_get_connector_missing_returns_none(db):
    assert ics.get_connector("nope") is None
