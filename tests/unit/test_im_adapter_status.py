"""Telegram adapter status reporting: connect/error/stopped + heartbeat.

These run without real platform sockets: create_app and the network-start seam are
mocked, and the connector store is stubbed so nothing touches the DB. (Slack no longer
reports owner-level status — it is per-agent; see test_slack_supervisor.py.)
"""

import asyncio

import pytest

import fleetent.im_gateway.telegram as telegram

_OWNER = "owner1"


def _stub_store(monkeypatch, mod, statuses, heartbeats):
    monkeypatch.setattr(
        mod.im_connector_store,
        "report_status",
        lambda o, p, s, error=None: statuses.append((p, s, error)),
    )
    monkeypatch.setattr(mod.im_connector_store, "heartbeat", lambda o, p: heartbeats.append(p))


async def test_telegram_run_reports_connected_then_error(monkeypatch):
    statuses: list = []
    _stub_store(monkeypatch, telegram, statuses, [])
    monkeypatch.setattr(telegram, "create_app", lambda owner_id, config: object())

    async def boom(app):
        raise RuntimeError("poll fail")

    monkeypatch.setattr(telegram, "_run_polling", boom)

    with pytest.raises(RuntimeError):
        await telegram.run(_OWNER, {"bot_token": "b"})

    assert ("telegram", "connected", None) in statuses
    assert ("telegram", "error", "poll fail") in statuses


async def test_telegram_run_heartbeats_then_stopped_on_cancel(monkeypatch):
    statuses: list = []
    heartbeats: list = []
    _stub_store(monkeypatch, telegram, statuses, heartbeats)
    monkeypatch.setattr(telegram, "create_app", lambda owner_id, config: object())
    monkeypatch.setattr(telegram, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def block(app):
        await asyncio.Event().wait()

    monkeypatch.setattr(telegram, "_run_polling", block)

    task = asyncio.create_task(telegram.run(_OWNER, {"bot_token": "b"}))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert ("telegram", "connected", None) in statuses
    assert ("telegram", "stopped", None) in statuses
    assert len(heartbeats) >= 1
