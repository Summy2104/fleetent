"""Adapters thread their task's owner_id onto inbound messages and status reports."""

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack
import fleetent.im_gateway.telegram as telegram


async def test_slack_handler_stamps_owner_and_agent(monkeypatch):
    routed = {}

    async def fake_route(msg):
        routed["owner_id"] = msg.owner_id
        routed["agent_name"] = msg.agent_name
        routed["user_id"] = msg.user_id

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    handler_holder = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            handler_holder["fn"] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app("support", "ownerA", {"bot_token": "b"})

    async def say(text, thread_ts=None):
        pass

    await handler_holder["fn"]({"user": "U1", "text": "hi", "ts": "1", "channel": "C1"}, say)
    assert routed["owner_id"] == "ownerA"
    assert routed["agent_name"] == "support"
    # Identity is the platform-native id resolved locally (no platform user_store).
    assert routed["user_id"] == "U1"


async def test_telegram_run_reports_status_with_owner(monkeypatch):
    statuses: list = []
    monkeypatch.setattr(
        telegram.im,
        "report_status",
        lambda o, p, s, error=None: statuses.append((o, p, s)),
    )
    monkeypatch.setattr(telegram.im, "heartbeat", lambda o, p: None)
    monkeypatch.setattr(telegram, "create_app", lambda owner_id, config: object())

    async def boom(app):
        raise RuntimeError("x")

    monkeypatch.setattr(telegram, "_run_polling", boom)

    import pytest

    with pytest.raises(RuntimeError):
        await telegram.run("ownerB", {"bot_token": "b"})
    assert ("ownerB", "telegram", "connected") in statuses
