"""IM user identity resolved locally — no platform user_store on the runtime path."""

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack
from fleetent.im_gateway.access import resolve_identity


def test_resolve_identity_returns_native_id():
    # The agent runtime uses the platform-native id directly as a stable identity.
    assert resolve_identity("slack", "U_alice") == "U_alice"
    assert resolve_identity("telegram", "12345") == "12345"


def _boom(*args, **kwargs):
    raise AssertionError("platform user_store must not be read on the runtime path")


def _build_slack_handler(monkeypatch, agent_name, owner_id, config):
    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    # Rig the platform identity store to raise on any access.
    monkeypatch.setattr("fleetent.platform.im_gateway_management.get_or_create", _boom)
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    holder = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            holder[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app(agent_name, owner_id, config)
    return holder["app_mention"], routed


async def _say(text, thread_ts=None):
    pass


async def test_slack_handler_resolves_identity_without_platform_db(monkeypatch):
    fn, routed = _build_slack_handler(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    # Must not raise (no platform user_store read) and must use the native slack id.
    await fn({"user": "U_native", "text": "hi", "ts": "1", "channel": "C1"}, _say)
    assert routed["msg"].user_id == "U_native"


async def test_telegram_handler_resolves_identity_without_platform_db(monkeypatch):
    import fleetent.im_gateway.telegram as telegram

    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.platform.im_gateway_management.get_or_create", _boom)
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    captured = {}

    class FakeApp:
        def add_handler(self, handler):
            captured["handler"] = handler

    class FakeBuilder:
        def token(self, t):
            return self

        def concurrent_updates(self, v):
            return self

        def build(self):
            return FakeApp()

    with patch("telegram.ext.Application") as app_cls:
        app_cls.builder.return_value = FakeBuilder()
        telegram.create_app("support", "ownerA", {"bot_token": "b"})

    handler = captured["handler"]
    fn = handler.callback

    # Build a minimal Update-like object.
    msg_text = MagicMock()
    msg_text.caption = None
    msg_text.text = "hi"
    msg_text.reply_to_message = None
    msg_text.chat.type = "private"
    msg_text.chat.id = 999
    msg_text.photo = None

    update = MagicMock()
    update.message = msg_text
    update.effective_user.id = 424242

    with patch("telegram.Update", MagicMock):
        await fn(update, MagicMock())

    assert routed["msg"].user_id == "424242"
