"""Adapters stamp the agent and the resolved user identity onto inbound messages.

The connector carries no owner_id (removed): the receiving connection identifies the
agent, identity is the platform-native id resolved locally, and there is no platform
user_store read.
"""

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack


async def test_slack_handler_stamps_agent_and_user(monkeypatch):
    routed = {}

    async def fake_route(msg):
        routed["agent_name"] = msg.agent_name
        routed["user_id"] = msg.user_id
        routed["has_owner_id"] = hasattr(msg, "owner_id")

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    handler_holder = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            handler_holder[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app("support", {"bot_token": "b"})

    async def say(text, thread_ts=None):
        pass

    await handler_holder["app_mention"](
        {"user": "U1", "text": "hi", "ts": "1", "channel": "C1"}, say
    )
    assert routed["agent_name"] == "support"
    # Identity is the platform-native id resolved locally (no platform user_store).
    assert routed["user_id"] == "U1"
    # owner_id is removed from the message contract entirely.
    assert routed["has_owner_id"] is False
