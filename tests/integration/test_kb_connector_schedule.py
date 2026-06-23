"""Integration tests: kb_connector_store schedule fields."""

from __future__ import annotations

import pytest

import fleetent.platform.knowledge_base_management.kb_connector_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def mgmt_db(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


def test_connector_schedule_defaults_null(mgmt_db):
    store.add_connector("c1", "google_drive", "t1", "kb1", {"folder_id": "F1"})
    row = store.get_connector("c1")
    assert row is not None
    assert row["sync_interval_seconds"] is None
    assert row["last_scheduled_sync_at"] is None


def test_connector_list_includes_schedule_fields(mgmt_db):
    store.add_connector("c2", "google_drive", "t1", "kb1", {"folder_id": "F2"})
    rows = store.list_connectors()
    c2 = next(r for r in rows if r["connector_id"] == "c2")
    assert "sync_interval_seconds" in c2
    assert "last_scheduled_sync_at" in c2


def test_edit_connector_set_sync_interval(mgmt_db):
    store.add_connector("c3", "google_drive", "t1", "kb1", {"folder_id": "F3"})
    store.edit_connector("c3", sync_interval_seconds=3600)
    row = store.get_connector("c3")
    assert row is not None
    assert row["sync_interval_seconds"] == 3600


def test_update_last_scheduled_sync_at(mgmt_db):
    store.add_connector("c4", "google_drive", "t1", "kb1", {"folder_id": "F4"})
    ts = "2026-06-23T00:00:00+00:00"
    store.update_last_scheduled_sync_at("c4", ts)
    row = store.get_connector("c4")
    assert row is not None
    assert row["last_scheduled_sync_at"] == ts


def test_list_schedulable_connectors_returns_only_with_interval(mgmt_db):
    store.add_connector("cs1", "google_drive", "t1", "kb1", {"folder_id": "FS1"})
    store.add_connector("cs2", "google_drive", "t1", "kb1", {"folder_id": "FS2"})
    store.add_connector("cs3", "confluence", "t1", "kb1", {"base_url": "http://x.com"})
    store.edit_connector("cs1", sync_interval_seconds=1800)
    store.edit_connector("cs3", sync_interval_seconds=7200)
    rows = store.list_schedulable_connectors()
    ids = {r["connector_id"] for r in rows}
    assert "cs1" in ids
    assert "cs3" in ids
    assert "cs2" not in ids
