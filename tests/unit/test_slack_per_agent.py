"""Per-agent Slack adapter: agent-keyed app, stamps agent and owner."""

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack


def _build_handlers(monkeypatch, agent_name, owner_id, config):
    """Capture all registered event handlers keyed by event name."""
    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    handlers = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            handlers[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app(agent_name, owner_id, config)
    return handlers, routed


async def _say(text, thread_ts=None):
    pass


async def test_create_app_stamps_agent_and_owner(monkeypatch):
    handlers, routed = _build_handlers(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    fn = handlers.get("app_mention") or handlers.get("message")
    await fn({"user": "U1", "text": "hi", "ts": "1", "channel": "C1"}, _say)
    msg = routed["msg"]
    assert msg.agent_name == "support"
    assert msg.owner_id == "ownerA"
    assert msg.platform == "slack"


async def test_app_mention_routes_to_normalizer(monkeypatch):
    """@mention in a channel triggers the handler."""
    handlers, routed = _build_handlers(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    assert "app_mention" in handlers, "app_mention handler must be registered"
    await handlers["app_mention"](
        {"user": "U1", "text": "<@BOTID> hello", "ts": "1", "channel": "C1"}, _say
    )
    assert routed["msg"].channel_id == "C1"


async def test_dm_message_routes_to_normalizer(monkeypatch):
    """DM (channel_type=im) still routes without @mention."""
    handlers, routed = _build_handlers(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    assert "message" in handlers, "message handler must be registered for DMs"
    await handlers["message"](
        {"user": "U1", "text": "hi", "ts": "1", "channel": "D123", "channel_type": "im"}, _say
    )
    assert routed["msg"].channel_id == "D123"


async def test_channel_message_without_mention_not_routed(monkeypatch):
    """Regular channel message (not @mention, not DM) is ignored."""
    handlers, routed = _build_handlers(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    if "message" in handlers:
        await handlers["message"](
            {"user": "U1", "text": "hi", "ts": "1", "channel": "C1", "channel_type": "channel"},
            _say,
        )
    assert "msg" not in routed


async def test_create_app_passes_all_channels_to_normalizer(monkeypatch):
    # Channel filtering now handled by the normalizer via ConnectorAccess.allow_channels,
    # not by the Slack handler; all @mention messages that arrive here are forwarded.
    handlers, routed = _build_handlers(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    fn = handlers.get("app_mention") or handlers.get("message")
    await fn({"user": "U1", "text": "hi", "ts": "1", "channel": "C99"}, _say)
    assert "msg" in routed
    assert routed["msg"].channel_id == "C99"
