"""Integration tests for outbound.send_file_to delivering a real local file.

Exercises the platform dispatch end-to-end against mock connectors using a real
file on disk (tmp_path), asserting the correct underlying connector method and
arguments per platform.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.outbound import send_file_to


async def test_slack_dm_delivers_real_file(tmp_path) -> None:
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 data")

    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_42"}})
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    ok = await send_file_to("slack", client, "U_RECIP", str(f))

    assert ok.ok is True
    client.conversations_open.assert_called_once_with(users=["U_RECIP"])
    client.files_upload_v2.assert_called_once_with(channel="DM_42", thread_ts=None, file=str(f))


async def test_slack_channel_threaded_delivers_real_file(tmp_path) -> None:
    f = tmp_path / "chart.png"
    f.write_bytes(b"PNG")

    client = AsyncMock()
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    ok = await send_file_to(
        "slack", client, "C_OPS", str(f), target_type="channel", thread="111.222"
    )

    assert ok.ok is True
    client.conversations_open.assert_not_called()
    client.files_upload_v2.assert_called_once_with(
        channel="C_OPS", thread_ts="111.222", file=str(f)
    )


async def test_telegram_delivers_real_file(tmp_path) -> None:
    f = tmp_path / "out.csv"
    f.write_text("a,b,c\n1,2,3\n")

    bot = AsyncMock()
    bot.send_document = AsyncMock()

    ok = await send_file_to("telegram", bot, "555", str(f))

    assert ok.ok is True
    bot.send_document.assert_called_once_with(chat_id="555", document=str(f))
