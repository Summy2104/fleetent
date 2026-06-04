import pytest

import fleetent.platform.im_gateway_management.channel_allowlist as acl
import fleetent.platform.im_gateway_management.connector_store as ics
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ics, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(acl, "DB_PATH", tmp_path / "users.db")
    acl._init_db()
    return tmp_path / "users.db"


def _columns(db_path):
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(im_channel_allowlist)").fetchall()}


def test_table_columns(db):
    assert {
        "id",
        "platform",
        "scope_type",
        "scope_id",
        "allowed",
        "note",
        "created_at",
    } <= _columns(db)


_OWNER = "owner1"


def test_add_entry_and_list(db):
    acl.add_entry(_OWNER, "slack", "channel", "C_ops", note="ops room")
    rows = acl.list_entries(_OWNER, "slack")
    assert len(rows) == 1
    assert rows[0]["scope_id"] == "C_ops"
    assert rows[0]["allowed"] == 1


def test_add_is_upsert(db):
    acl.add_entry(_OWNER, "slack", "channel", "C_ops")
    acl.add_entry(_OWNER, "slack", "channel", "C_ops", note="again")
    assert len(acl.list_entries(_OWNER, "slack")) == 1


def test_remove_entry(db):
    acl.add_entry(_OWNER, "slack", "channel", "C_ops")
    entry_id = acl.list_entries(_OWNER, "slack")[0]["id"]
    acl.remove_entry(entry_id)
    assert acl.list_entries(_OWNER, "slack") == []


def test_enforcement_disabled_allows_all(db):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=False)
    assert acl.is_allowed(_OWNER, "slack", "any_channel") is True


def test_enforcement_disabled_when_no_connector_row(db):
    # No connector row at all -> default allow (backward compatible)
    assert acl.is_allowed(_OWNER, "slack", "any_channel") is True


def test_enforced_channel_listed_allowed(db):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)
    acl.add_entry(_OWNER, "slack", "channel", "C_ops")
    assert acl.is_allowed(_OWNER, "slack", "C_ops") is True


def test_enforced_channel_not_listed_denied(db):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)
    assert acl.is_allowed(_OWNER, "slack", "C_random") is False


def test_workspace_entry_covers_its_channels(db):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)
    acl.add_entry(_OWNER, "slack", "workspace", "T_team")
    assert acl.is_allowed(_OWNER, "slack", "C_any", workspace_id="T_team") is True
    assert acl.is_allowed(_OWNER, "slack", "C_any", workspace_id="T_other") is False
