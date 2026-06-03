"""Per-owner adapter lifecycle in the connector manager."""

import asyncio

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import im_connector_config
from fleetent.platform.im_gateway_management import im_connector_manager as mgr
from fleetent.platform.im_gateway_management import im_connector_store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", p)
    monkeypatch.setattr(store, "DB_PATH", p)
    # every owner resolves config (skip admin-only env gating for this test)
    monkeypatch.setattr(
        im_connector_config, "resolve", lambda owner_id, platform: {"bot_token": "t"}
    )
    return p


def _recording_factory(calls):
    async def factory(owner_id, config):
        calls.append((owner_id, config))
        await asyncio.Event().wait()  # run until cancelled

    return factory


async def test_concurrent_owners_same_platform(db):
    calls: list = []
    m = mgr.ConnectorManager({"telegram": _recording_factory(calls)})
    await m.start("ownerA", "telegram")
    await m.start("ownerB", "telegram")
    await asyncio.sleep(0)
    assert m.running() == {("ownerA", "telegram"), ("ownerB", "telegram")}
    assert {c[0] for c in calls} == {"ownerA", "ownerB"}
    await m.stop("ownerA", "telegram")
    assert m.running() == {("ownerB", "telegram")}
    await m.stop("ownerB", "telegram")


async def test_unconfigured_when_no_config(db, monkeypatch):
    monkeypatch.setattr(im_connector_config, "resolve", lambda owner_id, platform: {})
    m = mgr.ConnectorManager({"telegram": _recording_factory([])})
    await m.start("ownerA", "telegram")
    assert m.running() == set()
    assert store.get_connector("ownerA", "telegram")["status"] == "unconfigured"


async def test_start_all_enabled_spans_owners(db):
    store.upsert_connector("ownerA", "telegram", enabled=True)
    store.upsert_connector("ownerB", "telegram", enabled=True)
    store.upsert_connector("ownerC", "telegram", enabled=False)
    m = mgr.ConnectorManager({"telegram": _recording_factory([])})
    await m.start_all_enabled()
    await asyncio.sleep(0)
    assert m.running() == {("ownerA", "telegram"), ("ownerB", "telegram")}
    for o in ("ownerA", "ownerB"):
        await m.stop(o, "telegram")
