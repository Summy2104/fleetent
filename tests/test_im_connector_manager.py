import asyncio
from types import SimpleNamespace

import pytest

import fleetent.im_connector_config as icc
import fleetent.im_connector_manager as mgr
import fleetent.im_connector_store as ics
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ics, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(icc, "get_settings", lambda: SimpleNamespace(
        slack_bot_token="", slack_app_token="", telegram_bot_token=""))
    ics._init_db()
    return tmp_path / "users.db"


def _blocking_factory(started: asyncio.Event):
    async def run(config):
        started.set()
        await asyncio.Event().wait()  # run until cancelled
    return run


async def test_start_creates_running_task(db):
    ics.upsert_connector("slack", config='{"bot_token": "x"}')
    started = asyncio.Event()
    m = mgr.ConnectorManager(factories={"slack": _blocking_factory(started)})
    await m.start("slack")
    await asyncio.wait_for(started.wait(), timeout=1)
    assert "slack" in m.running()
    await m.stop("slack")


async def test_unconfigured_when_no_factory(db):
    ics.upsert_connector("slack", config='{"bot_token": "x"}')
    m = mgr.ConnectorManager(factories={})  # no adapter for slack
    await m.start("slack")
    assert "slack" not in m.running()
    assert ics.get_connector("slack")["status"] == "unconfigured"


async def test_unconfigured_when_no_config(db):
    ics.upsert_connector("whatsapp")  # no config, env empty
    started = asyncio.Event()
    m = mgr.ConnectorManager(factories={"whatsapp": _blocking_factory(started)})
    await m.start("whatsapp")
    assert "whatsapp" not in m.running()
    assert ics.get_connector("whatsapp")["status"] == "unconfigured"


async def test_stop_cancels_and_sets_stopped(db):
    ics.upsert_connector("slack", config='{"bot_token": "x"}')
    started = asyncio.Event()
    m = mgr.ConnectorManager(factories={"slack": _blocking_factory(started)})
    await m.start("slack")
    await asyncio.wait_for(started.wait(), timeout=1)
    await m.stop("slack")
    assert "slack" not in m.running()
    assert ics.get_connector("slack")["status"] == "stopped"


async def test_duplicate_start_no_double_task(db):
    ics.upsert_connector("slack", config='{"bot_token": "x"}')
    started = asyncio.Event()
    m = mgr.ConnectorManager(factories={"slack": _blocking_factory(started)})
    await m.start("slack")
    await asyncio.wait_for(started.wait(), timeout=1)
    t1 = m._tasks["slack"]
    await m.start("slack")
    assert m._tasks["slack"] is t1
    await m.stop("slack")


async def test_factory_error_sets_error_status(db):
    ics.upsert_connector("slack", config='{"bot_token": "x"}')

    async def boom(config):
        raise RuntimeError("connect failed")

    m = mgr.ConnectorManager(factories={"slack": boom})
    await m.start("slack")
    await asyncio.sleep(0.05)
    row = ics.get_connector("slack")
    assert row["status"] == "error"
    assert "connect failed" in row["last_error"]


async def test_start_all_enabled_only_enabled(db):
    ics.upsert_connector("slack", enabled=True, config='{"bot_token": "x"}')
    ics.upsert_connector("telegram", enabled=False, config='{"bot_token": "y"}')
    s1, s2 = asyncio.Event(), asyncio.Event()
    m = mgr.ConnectorManager(
        factories={"slack": _blocking_factory(s1), "telegram": _blocking_factory(s2)}
    )
    await m.start_all_enabled()
    await asyncio.wait_for(s1.wait(), timeout=1)
    assert "slack" in m.running()
    assert "telegram" not in m.running()
    await m.stop("slack")
