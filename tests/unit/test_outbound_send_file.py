"""Unit tests for the unified outbound file primitive (sandbox-file-egress).

`outbound.send_file_to` dispatches by platform: Slack -> files_upload_v2,
Telegram -> bot.send_document. Connector errors return False, never raise.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock


async def test_send_file_to_slack_channel_uploads_to_channel() -> None:
    from fleetent.outbound import send_file_to

    client = AsyncMock()
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    result = await send_file_to(
        "slack", client, "C_CHAN", "/tmp/report.pdf", target_type="channel", thread="1.2"
    )

    assert result is True
    client.files_upload_v2.assert_called_once_with(
        channel="C_CHAN", thread_ts="1.2", file="/tmp/report.pdf"
    )


async def test_send_file_to_slack_user_opens_dm_then_uploads() -> None:
    from fleetent.outbound import send_file_to

    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_X"}})
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    result = await send_file_to("slack", client, "U_USER", "/tmp/out.csv")

    assert result is True
    client.conversations_open.assert_called_once_with(users=["U_USER"])
    client.files_upload_v2.assert_called_once_with(
        channel="DM_X", thread_ts=None, file="/tmp/out.csv"
    )


async def test_send_file_to_slack_returns_false_on_failure() -> None:
    from fleetent.outbound import send_file_to

    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_X"}})
    client.files_upload_v2 = AsyncMock(side_effect=RuntimeError("boom"))

    result = await send_file_to("slack", client, "U_USER", "/tmp/out.csv")

    assert result is False


async def test_send_file_to_telegram_calls_send_document() -> None:
    from fleetent.outbound import send_file_to

    bot = AsyncMock()
    bot.send_document = AsyncMock(return_value=MagicMock())

    result = await send_file_to("telegram", bot, "987", "/tmp/out.csv")

    assert result is True
    bot.send_document.assert_called_once_with(chat_id="987", document="/tmp/out.csv")


async def test_send_file_to_telegram_returns_false_on_failure() -> None:
    from fleetent.outbound import send_file_to

    bot = AsyncMock()
    bot.send_document = AsyncMock(side_effect=RuntimeError("forbidden"))

    result = await send_file_to("telegram", bot, "987", "/tmp/out.csv")

    assert result is False


async def test_send_file_to_unknown_platform_returns_false() -> None:
    from fleetent.outbound import send_file_to

    result = await send_file_to("whatsapp", MagicMock(), "x", "/tmp/out.csv")
    assert result is False


def test_send_file_to_reexported_by_im_gateway_shim() -> None:
    from fleetent.im_gateway.outbound import send_file_to as shim_fn
    from fleetent.outbound import send_file_to as real_fn

    assert shim_fn is real_fn


def test_outbound_module_has_no_platform_imports() -> None:
    import fleetent.outbound as outbound_mod

    source = inspect.getsource(outbound_mod)
    assert "fleetent.platform" not in source
