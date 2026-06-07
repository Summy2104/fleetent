"""Per-agent Telegram adapter: agent-keyed app, stamps agent, channel filter, no platform."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.im_gateway.telegram as telegram


def _capture_handler(monkeypatch, agent_name, owner_id, config):
    """Build the telegram app with a mocked Application builder; capture the handler."""
    mock_app = MagicMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.concurrent_updates.return_value = mock_builder
    mock_builder.build.return_value = mock_app

    with patch("telegram.ext.Application") as mock_cls:
        mock_cls.builder.return_value = mock_builder
        telegram.create_app(agent_name, owner_id, config)

    return mock_app.add_handler.call_args[0][0]


def _private_update(chat_id, text="hi"):
    from telegram import Update

    update = MagicMock(spec=Update)
    eff_user = MagicMock()
    eff_user.id = 555
    update.effective_user = eff_user
    msg = MagicMock()
    msg.reply_to_message = None
    chat = MagicMock()
    chat.type = "private"
    chat.id = chat_id
    msg.chat = chat
    msg.caption = None
    msg.text = text
    msg.photo = None
    msg.reply_text = AsyncMock()
    update.message = msg
    return update


async def _run(handler_obj, update, monkeypatch):
    import fleetent.im_gateway.normalizer as norm

    captured = AsyncMock()
    monkeypatch.setattr(norm, "route", captured)
    await handler_obj.callback(update, MagicMock())
    return captured


async def test_create_app_stamps_agent_and_owner(monkeypatch):
    handler = _capture_handler(monkeypatch, "sales", "ownerA", {"bot_token": "b"})
    captured = await _run(handler, _private_update("-100123"), monkeypatch)
    captured.assert_called_once()
    msg = captured.call_args[0][0]
    assert msg.agent_name == "sales"
    assert msg.owner_id == "ownerA"
    assert msg.platform == "telegram"


async def test_channel_filter_drops_unlisted(monkeypatch):
    handler = _capture_handler(
        monkeypatch, "sales", "ownerA", {"bot_token": "b", "channels": ["-100123"]}
    )
    captured = await _run(handler, _private_update("-100999"), monkeypatch)
    captured.assert_not_called()  # chat outside the filter


async def test_channel_filter_empty_allows_all(monkeypatch):
    handler = _capture_handler(monkeypatch, "sales", "ownerA", {"bot_token": "b", "channels": []})
    captured = await _run(handler, _private_update("-100999"), monkeypatch)
    captured.assert_called_once()


def test_adapter_has_no_platform_import():
    assert "fleetent.platform" not in inspect.getsource(telegram)
