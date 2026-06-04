"""Per-agent Slack adapter: agent-keyed app, stamps agent, channel filter."""

from unittest.mock import MagicMock, patch

import fleetent.im_gateway.slack as slack


def _build_handler(monkeypatch, agent_name, owner_id, config):
    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    holder = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            holder["fn"] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app(agent_name, owner_id, config)
    return holder["fn"], routed


async def _say(text, thread_ts=None):
    pass


async def test_create_app_stamps_agent_and_owner(monkeypatch):
    fn, routed = _build_handler(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "app_token": "a"}
    )
    await fn({"user": "U1", "text": "hi", "ts": "1", "channel": "C1"}, _say)
    msg = routed["msg"]
    assert msg.agent_name == "support"
    assert msg.owner_id == "ownerA"
    assert msg.platform == "slack"


async def test_channel_filter_drops_unlisted(monkeypatch):
    fn, routed = _build_handler(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "channels": ["C1"]}
    )
    await fn({"user": "U1", "text": "hi", "ts": "1", "channel": "C2"}, _say)
    assert "msg" not in routed  # dropped: C2 not in the filter


async def test_channel_filter_empty_allows_all(monkeypatch):
    fn, routed = _build_handler(
        monkeypatch, "support", "ownerA", {"bot_token": "b", "channels": []}
    )
    await fn({"user": "U1", "text": "hi", "ts": "1", "channel": "C9"}, _say)
    assert "msg" in routed
