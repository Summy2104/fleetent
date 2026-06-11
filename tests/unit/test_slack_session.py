"""Session-id derivation for Slack: thread-first, keyed by the thread root."""

from __future__ import annotations

from fleetent.im_gateway.slack import _derive_session_id


def test_dm_top_level_keyed_by_own_ts():
    # A top-level DM message: bot threads on it, session keyed by that ts.
    assert (
        _derive_session_id(channel_type="im", channel_id="D1", user_id="U123", thread_root="100.1")
        == "slack:dm:U123:100.1"
    )


def test_dm_followup_in_thread_same_session():
    # Follow-up inside the bot-created thread resolves to the same key.
    top = _derive_session_id(
        channel_type="im", channel_id="D1", user_id="U123", thread_root="100.1"
    )
    followup = _derive_session_id(
        channel_type="im", channel_id="D1", user_id="U123", thread_root="100.1"
    )
    assert top == followup == "slack:dm:U123:100.1"


def test_assistant_new_conversation_new_session():
    a = _derive_session_id(channel_type="im", channel_id="D1", user_id="U123", thread_root="200.2")
    b = _derive_session_id(channel_type="im", channel_id="D1", user_id="U123", thread_root="100.1")
    assert a != b  # different assistant threads → different sessions


def test_channel_keyed_by_thread_root():
    assert (
        _derive_session_id(
            channel_type="channel", channel_id="C9", user_id="U123", thread_root="300.3"
        )
        == "slack:thread:C9:300.3"
    )


def test_channel_top_level_and_thread_share_session():
    top = _derive_session_id(
        channel_type="channel", channel_id="C9", user_id="U123", thread_root="300.3"
    )
    in_thread = _derive_session_id(
        channel_type="channel", channel_id="C9", user_id="U999", thread_root="300.3"
    )
    # Shared by thread root regardless of which user replies.
    assert top == in_thread == "slack:thread:C9:300.3"


def test_dm_and_channel_do_not_collide():
    dm = _derive_session_id(channel_type="im", channel_id="D1", user_id="U123", thread_root="50.0")
    ch = _derive_session_id(
        channel_type="channel", channel_id="C9", user_id="U123", thread_root="50.0"
    )
    assert dm != ch
    assert dm.startswith("slack:dm:") and ch.startswith("slack:thread:")


# ── session_context field + adapter population ───────────────────────────────

from unittest.mock import AsyncMock, MagicMock  # noqa: E402


def test_normalized_message_session_context_default_none():
    from fleetent.im_gateway.normalizer import NormalizedMessage

    async def _r(t: str) -> None:
        pass

    msg = NormalizedMessage(
        platform="slack", session_id="s", user_id="u", text="hi", attachments=[], reply_func=_r
    )
    assert msg.session_context is None


def test_session_context_dataclass_fields():
    from fleetent.im_gateway.normalizer import SessionContext

    sc = SessionContext(platform="slack", sender_id="U1")
    assert sc.platform == "slack"
    assert sc.sender_id == "U1"
    assert sc.chat_type == "dm"
    assert sc.was_mentioned is False


def _capture_routed(monkeypatch):
    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )
    monkeypatch.setattr(
        "fleetent.im_gateway.slack._download_attachments", AsyncMock(return_value=[])
    )
    return routed


async def test_assistant_message_populates_session_context(monkeypatch):
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    ctx = MagicMock()
    ctx.channel_id = "D1"
    ctx.thread_ts = "200.2"
    await slack_mod._route_assistant_message(
        payload={"user": "U123", "text": "hi"},
        context=ctx,
        set_status=AsyncMock(),
        say=AsyncMock(),
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )
    sc = routed["msg"].session_context
    assert sc is not None
    assert sc.platform == "slack"
    assert sc.sender_id == "U123"
    assert sc.chat_type == "dm"
