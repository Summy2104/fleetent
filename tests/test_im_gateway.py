import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from mini_agent.im_gateway.normalizer import NormalizedMessage, route


@pytest.fixture
def mock_session_mgr(monkeypatch):
    import mini_agent.session_mgr as sm
    monkeypatch.setattr(sm, "load", AsyncMock(return_value=[]))
    monkeypatch.setattr(sm, "save", AsyncMock())
    return sm


@pytest.fixture
def mock_agent_loop(monkeypatch):
    import mini_agent.agent_loop as al
    monkeypatch.setattr(al, "run", AsyncMock(return_value="agent response"))
    return al


async def test_route_loads_history_calls_agent_saves_replies(mock_session_mgr, mock_agent_loop):
    reply_calls = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U123",
        user_id="internal-user-1",
        text="hello",
        attachments=[],
        reply_func=fake_reply,
    )

    await route(msg)

    mock_session_mgr.load.assert_called_once_with("user:U123")
    mock_agent_loop.run.assert_called_once()
    mock_session_mgr.save.assert_called_once()
    assert reply_calls == ["agent response"]


async def test_slack_dm_session_id():
    from mini_agent.im_gateway.slack import _derive_session_id
    assert _derive_session_id(user_id="U123", channel_type="im", thread_ts=None) == "user:U123"


async def test_slack_thread_session_id():
    from mini_agent.im_gateway.slack import _derive_session_id
    assert _derive_session_id(user_id="U123", channel_type="channel", thread_ts="T456") == "thread:T456"


async def test_slack_channel_no_thread():
    from mini_agent.im_gateway.slack import _derive_session_id
    # No thread_ts in a channel message → use user session as fallback
    result = _derive_session_id(user_id="U123", channel_type="channel", thread_ts=None)
    # Should return something non-None (either user: or create a new thread)
    assert result.startswith("user:") or result.startswith("thread:")


async def test_telegram_private_session_id():
    from mini_agent.im_gateway.telegram import _derive_session_id
    assert _derive_session_id(chat_type="private", user_id=12345, reply_to_id=None) == "user:12345"


async def test_telegram_group_reply_session_id():
    from mini_agent.im_gateway.telegram import _derive_session_id
    assert _derive_session_id(chat_type="group", user_id=12345, reply_to_id=999) == "thread:999"
