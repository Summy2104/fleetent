"""Integration tests: Slack/Telegram adapter file egress via the unified primitive.

slack._make_upload_func converges onto outbound.send_file_to (behavior unchanged:
same files_upload_v2 call, per-file graceful degrade). Telegram DM send_file routes
through the unified primitive to bot.send_document.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.im_gateway.normalizer import SessionContext
from fleetent.integrations.sandbox import Scope
from fleetent.tools.registry import ToolContext

# ── 4.1/4.2 Slack adapter converges onto unified primitive ───────────────────


async def test_slack_make_upload_func_uploads_via_files_upload_v2(tmp_path) -> None:
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNG")

    from fleetent.im_gateway import slack as slack_mod

    client = MagicMock()
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    upload_func = slack_mod._make_upload_func(
        client=client, channel="C_INBOUND", reply_thread="9.9"
    )
    await upload_func([str(img)])

    client.files_upload_v2.assert_called_once_with(
        channel="C_INBOUND", thread_ts="9.9", file=str(img)
    )


async def test_slack_make_upload_func_degrades_per_file(tmp_path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"A")
    b.write_bytes(b"B")

    from fleetent.im_gateway import slack as slack_mod

    uploaded: list[str] = []
    client = MagicMock()

    async def fake_upload(**kwargs):
        if "a.png" in kwargs["file"]:
            raise RuntimeError("fail")
        uploaded.append(kwargs["file"])

    client.files_upload_v2 = fake_upload

    upload_func = slack_mod._make_upload_func(client=client, channel="C", reply_thread=None)
    await upload_func([str(a), str(b)])

    assert str(b) in uploaded
    assert str(a) not in uploaded


# ── 4.3/4.4 Telegram DM send_file routes through send_document ───────────────


async def test_telegram_send_file_routes_to_send_document(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "out.csv").write_text("a,b\n1,2\n")

    bot = MagicMock()
    bot.send_document = AsyncMock()

    manager = MagicMock()
    manager.scope = Scope.SESSION
    manager.workspace_host_path.return_value = tmp_path

    ctx = ToolContext(
        session_id="user:555",
        session_context=SessionContext(platform="telegram", sender_id="555", chat_type="dm"),
        outbound_connectors={"telegram": bot},
    )
    with patch("fleetent.tools.builtin_tools._get_manager", return_value=manager):
        result = await send_file(path="out.csv", tool_context=ctx)

    bot.send_document.assert_called_once_with(chat_id="555", document=str(tmp_path / "out.csv"))
    assert "telegram:555" in result
