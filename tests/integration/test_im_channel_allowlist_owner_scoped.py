"""Owner-scoped IM channel/workspace allowlist."""

import pytest

from fleetent.platform.im_gateway_management import channel_allowlist as al
from fleetent.platform.im_gateway_management import connector_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    apply_migrations(p)
    return p


def test_entries_isolated_per_owner(db):
    al.add_entry("ownerA", "slack", "channel", "C1")
    al.add_entry("ownerB", "slack", "channel", "C2")
    assert {e["scope_id"] for e in al.list_entries("ownerA")} == {"C1"}
    assert {e["scope_id"] for e in al.list_entries("ownerB")} == {"C2"}


def test_is_allowed_scoped_by_owner(db):
    # enforce allowlist for owner A's slack connector
    store.upsert_connector("ownerA", "slack", allowlist_enforced=True)
    store.upsert_connector("ownerB", "slack", allowlist_enforced=True)
    al.add_entry("ownerA", "slack", "channel", "C1")
    assert al.is_allowed("ownerA", "slack", "C1") is True
    # owner B has no entry for C1 → denied under its own enforcement
    assert al.is_allowed("ownerB", "slack", "C1") is False


def test_not_enforced_allows_all(db):
    store.upsert_connector("ownerA", "slack", allowlist_enforced=False)
    assert al.is_allowed("ownerA", "slack", "anything") is True
