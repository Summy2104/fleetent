"""Owner-keyed IM connector registry CRUD."""

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import im_connector_store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", p)
    monkeypatch.setattr(store, "DB_PATH", p)
    return p


def test_two_owners_same_platform_coexist(db):
    store.upsert_connector("ownerA", "slack", enabled=True)
    store.upsert_connector("ownerB", "slack", enabled=False)
    a = store.get_connector("ownerA", "slack")
    b = store.get_connector("ownerB", "slack")
    assert a is not None and a["owner_id"] == "ownerA" and a["enabled"] == 1
    assert b is not None and b["owner_id"] == "ownerB" and b["enabled"] == 0


def test_upsert_updates_same_owner_platform(db):
    store.upsert_connector("ownerA", "slack", enabled=False)
    store.upsert_connector("ownerA", "slack", enabled=True)
    rows = store.list_connectors("ownerA")
    assert len(rows) == 1
    assert rows[0]["enabled"] == 1


def test_list_filters_by_owner(db):
    store.upsert_connector("ownerA", "slack")
    store.upsert_connector("ownerB", "telegram")
    assert {r["platform"] for r in store.list_connectors("ownerA")} == {"slack"}
    assert {r["platform"] for r in store.list_connectors("ownerB")} == {"telegram"}


def test_list_all_for_admin(db):
    store.upsert_connector("ownerA", "slack")
    store.upsert_connector("ownerB", "telegram")
    rows = store.list_connectors(None)
    assert {(r["owner_id"], r["platform"]) for r in rows} == {
        ("ownerA", "slack"),
        ("ownerB", "telegram"),
    }


def test_status_heartbeat_flags_owner_scoped(db):
    store.upsert_connector("ownerA", "slack")
    store.report_status("ownerA", "slack", "connected")
    store.set_enabled("ownerA", "slack", True)
    store.set_allowlist_enforced("ownerA", "slack", True)
    store.heartbeat("ownerA", "slack")
    row = store.get_connector("ownerA", "slack")
    assert row["status"] == "connected"
    assert row["enabled"] == 1
    assert row["allowlist_enforced"] == 1
    assert row["last_heartbeat_at"] is not None


def test_get_missing_returns_none(db):
    store.upsert_connector("ownerA", "slack")
    assert store.get_connector("ownerA", "telegram") is None
    assert store.get_connector("ownerZ", "slack") is None
