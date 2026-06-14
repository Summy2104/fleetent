"""Slack inbound builds a ConversationAddress on the NormalizedMessage (conversation-address)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack


def _build_handlers(monkeypatch):
    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity",
        lambda p, uid, owner_id="default": uid,
        raising=False,
    )
    handlers: dict = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            handlers[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app("my-bot", {"bot_token": "b", "app_token": "a"})
    return handlers, routed


async def _say(text="", thread_ts=None, **kwargs):
    pass


async def test_channel_mention_address_carries_thread(monkeypatch):
    handlers, routed = _build_handlers(monkeypatch)
    event = {"user": "U1", "text": "<@B> hi", "ts": "300.3", "channel": "C9"}
    await handlers["app_mention"](event, MagicMock(), _say)

    addr = routed["msg"].conversation_address
    assert addr is not None
    assert addr.platform == "slack"
    assert addr.chat_id == "C9"
    assert addr.target_type == "channel"
    assert addr.thread_id == "300.3"  # threads on the message ts
    assert addr.chat_type == "channel"
    assert addr.user_id == "U1"


async def test_dm_address_threaded_on_ts(monkeypatch):
    handlers, routed = _build_handlers(monkeypatch)
    event = {"user": "U1", "text": "hi", "ts": "100.1", "channel": "D1", "channel_type": "im"}
    await handlers["message"](event, MagicMock(), _say)

    addr = routed["msg"].conversation_address
    assert addr is not None
    assert addr.platform == "slack"
    assert addr.chat_id == "D1"
    assert addr.thread_id == "100.1"
    assert addr.chat_type == "dm"
