from unittest.mock import AsyncMock

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


@pytest.fixture
def mock_memory_skill(monkeypatch):
    import mini_agent.memory_layer as ml
    import mini_agent.skill_registry as sr
    monkeypatch.setattr(ml, "load_memories", lambda **kwargs: "")
    monkeypatch.setattr(sr, "match", lambda text: None)


async def test_route_loads_history_calls_agent_saves_replies(
    mock_session_mgr, mock_agent_loop, mock_memory_skill
):
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
    # system message inserted + user message appended → messages passed to run()
    call_messages = mock_agent_loop.run.call_args[1]["messages"]
    assert call_messages[0]["role"] == "system"
    assert call_messages[-1] == {"role": "user", "content": "hello"}
    mock_session_mgr.save.assert_called_once()
    assert reply_calls == ["agent response"]


async def test_approve_command_resolves_gate_and_does_not_call_agent(
    mock_session_mgr, mock_agent_loop, mock_memory_skill
):
    from unittest.mock import AsyncMock, patch

    from mini_agent.im_gateway.normalizer import NormalizedMessage, route

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U123",
        user_id="approver-1",
        text="approve abc12345",
        attachments=[],
        reply_func=fake_reply,
    )

    mock_resolve = AsyncMock()
    with patch("mini_agent.permission_gate._default_gate") as mock_gate:
        mock_gate.resolve = mock_resolve
        await route(msg)

    mock_resolve.assert_called_once_with(
        approval_id="abc12345",
        decision="approved",
        approver_user_id="approver-1",
    )
    mock_agent_loop.run.assert_not_called()
    assert "abc12345" in reply_calls[0]
    assert "approved" in reply_calls[0]


async def test_reject_command_resolves_gate(mock_session_mgr, mock_agent_loop, mock_memory_skill):
    from unittest.mock import AsyncMock, patch

    from mini_agent.im_gateway.normalizer import NormalizedMessage, route

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    msg = NormalizedMessage(
        platform="telegram",
        session_id="user:999",
        user_id="approver-2",
        text="reject abc12345",
        attachments=[],
        reply_func=fake_reply,
    )

    mock_resolve = AsyncMock()
    with patch("mini_agent.permission_gate._default_gate") as mock_gate:
        mock_gate.resolve = mock_resolve
        await route(msg)

    mock_resolve.assert_called_once_with(
        approval_id="abc12345",
        decision="rejected",
        approver_user_id="approver-2",
    )
    mock_agent_loop.run.assert_not_called()
    assert "rejected" in reply_calls[0]


async def test_slack_dm_session_id():
    from mini_agent.im_gateway.slack import _derive_session_id
    assert _derive_session_id(user_id="U123", channel_type="im", thread_ts=None) == "user:U123"


async def test_slack_thread_session_id():
    from mini_agent.im_gateway.slack import _derive_session_id
    result = _derive_session_id(user_id="U123", channel_type="channel", thread_ts="T456")
    assert result == "thread:T456"


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


async def test_telegram_group_no_reply_falls_back_to_user_session():
    from mini_agent.im_gateway.telegram import _derive_session_id

    # group message with no reply_to_id → user session (line 15 in telegram.py)
    result = _derive_session_id(chat_type="group", user_id=99, reply_to_id=None)
    assert result == "user:99"


async def test_slack_create_app_returns_app_object(monkeypatch):
    """create_app() instantiates a bolt App and registers the message handler."""
    from unittest.mock import MagicMock, patch

    mock_app_instance = MagicMock()
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")

    # AsyncApp is imported inside create_app() via `from slack_bolt.async_app import AsyncApp`
    with patch("slack_bolt.async_app.AsyncApp", return_value=mock_app_instance) as mock_app_cls:
        import mini_agent.im_gateway.slack as slack_mod

        result = slack_mod.create_app()

    assert result is mock_app_instance
    mock_app_cls.assert_called_once_with(token="xoxb-fake")
    mock_app_instance.event.assert_called_once_with("message")


async def test_telegram_create_app_returns_application_object(monkeypatch):
    """create_app() builds a telegram Application and registers a message handler."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-fake-token")

    mock_app = MagicMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.concurrent_updates.return_value = mock_builder
    mock_builder.build.return_value = mock_app

    # Application is imported inside create_app() via `from telegram.ext import Application`
    with patch("telegram.ext.Application") as mock_cls:
        mock_cls.builder.return_value = mock_builder
        import mini_agent.im_gateway.telegram as tg_mod

        result = tg_mod.create_app()

    assert result is mock_app
    mock_app.add_handler.assert_called_once()


async def test_route_uses_agent_system_prompt_and_allowed_tools(
    mock_session_mgr, mock_agent_loop, mock_memory_skill, monkeypatch
):
    """route() should pass agent's system_prompt and allowed_tools when an agent is assigned."""
    from mini_agent.agent_store import Agent
    import mini_agent.im_gateway.normalizer as norm

    fake_agent = Agent(
        id=1,
        name="restricted",
        system_prompt="You are a restricted agent.",
        allowed_tools=["calculate"],
    )
    monkeypatch.setattr(norm, "get_agent_for_user", lambda user_id: fake_agent)

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U999",
        user_id="restricted-user",
        text="hi",
        attachments=[],
        reply_func=fake_reply,
    )

    await route(msg)

    call_kwargs = mock_agent_loop.run.call_args[1]
    assert call_kwargs["allowed_tools"] == ["calculate"]
    system_msg = call_kwargs["messages"][0]
    assert "restricted agent" in system_msg["content"]


async def test_route_no_agent_passes_none_allowed_tools(
    mock_session_mgr, mock_agent_loop, mock_memory_skill, monkeypatch
):
    """When no agent is assigned, allowed_tools should be None (all tools available)."""
    import mini_agent.im_gateway.normalizer as norm

    monkeypatch.setattr(norm, "get_agent_for_user", lambda user_id: None)

    async def fake_reply(text: str) -> None:
        pass

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U000",
        user_id="free-user",
        text="hi",
        attachments=[],
        reply_func=fake_reply,
    )

    await route(msg)

    call_kwargs = mock_agent_loop.run.call_args[1]
    assert call_kwargs["allowed_tools"] is None
