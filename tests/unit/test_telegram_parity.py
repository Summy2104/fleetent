"""Unit: Telegram parity edge — reply buttons, approval callback, document inbound, upload_func.

All external surfaces (telegram bot, neutral approval components) are stubbed/mocked; no
network, no real DB. Mirrors Slack's approval-button + file-inbound + generated-image-upload
behavior on the Telegram adapter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.im_gateway.telegram as tg
from fleetent.outbound import ApprovalPrompt, parse_approval_callback


# ── Group 3: reply with optional approval keyboard ────────────────────────────


async def test_reply_plain_text_no_markup():
    message = MagicMock()
    message.reply_text = AsyncMock()
    await tg._send_reply(message, "hello")
    _, kwargs = message.reply_text.call_args
    assert kwargs.get("reply_markup") is None


async def test_reply_with_approval_attaches_inline_keyboard():
    message = MagicMock()
    message.reply_text = AsyncMock()
    ap = ApprovalPrompt(approval_id="a1", tool_name="run_code", risk_level="medium", summary="")
    await tg._send_reply(message, "approve?", approval=ap)
    _, kwargs = message.reply_text.call_args
    markup = kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert {parse_approval_callback(b.callback_data)[0] for b in buttons} == {
        "approve",
        "reject",
        "approve_always",
    }


# ── Group 4: approval callback handler ────────────────────────────────────────


def _callback_update(data: str, clicker: int = 123):
    update = MagicMock()
    cq = update.callback_query
    cq.data = data
    cq.from_user.id = clicker
    cq.answer = AsyncMock()
    cq.message.edit_text = AsyncMock()
    cq.message.chat.id = 555
    return update


@pytest.fixture
def _mock_neutral(monkeypatch):
    from fleetent.governance import approval_router, approval_store
    from fleetent.im_gateway import normalizer
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(approval_store, "get_approval", MagicMock(return_value={"session_id": "s1"}))
    monkeypatch.setattr(
        session_mgr, "get_pending_approval", AsyncMock(return_value={"approver_ids": ["123"]})
    )
    resolve = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_router, "resolve_approval_request", resolve)
    resume = AsyncMock()
    monkeypatch.setattr(normalizer, "_resume_pending_in_session", resume)
    return {"resolve": resolve, "resume": resume}


async def test_callback_ignores_non_approval_data(_mock_neutral):
    update = _callback_update("clarify:s1:0")
    await tg.handle_approval_callback(update, MagicMock(), "bot")
    _mock_neutral["resolve"].assert_not_called()


async def test_callback_authorized_resolves_edits_and_resumes(_mock_neutral):
    update = _callback_update("approval:approve:appr1")
    await tg.handle_approval_callback(update, MagicMock(), "bot")
    _mock_neutral["resolve"].assert_awaited()
    assert _mock_neutral["resolve"].call_args.kwargs["decision"] == "approved"
    update.callback_query.message.edit_text.assert_awaited()  # keyboard removed
    _mock_neutral["resume"].assert_awaited()


async def test_callback_unauthorized_alerts_no_resume(monkeypatch, _mock_neutral):
    _mock_neutral["resolve"].return_value = False  # not found / not authorized
    update = _callback_update("approval:reject:appr1")
    await tg.handle_approval_callback(update, MagicMock(), "bot")
    update.callback_query.answer.assert_awaited()
    assert update.callback_query.answer.call_args.kwargs.get("show_alert") is True
    _mock_neutral["resume"].assert_not_awaited()
    update.callback_query.message.edit_text.assert_not_awaited()


async def test_callback_resume_failure_does_not_raise(_mock_neutral):
    _mock_neutral["resume"].side_effect = RuntimeError("boom")
    update = _callback_update("approval:approve:appr1")
    await tg.handle_approval_callback(update, MagicMock(), "bot")  # must not raise


# ── Group 5: non-image document inbound ───────────────────────────────────────


def _doc_message(file_size=1000, mime="application/pdf", filename="r.pdf"):
    message = MagicMock()
    message.document = MagicMock(file_size=file_size, mime_type=mime, file_name=filename, file_id="f1")
    return message


async def test_document_downloaded_as_file_attachment():
    message = _doc_message()
    context = MagicMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"PDFDATA"))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    atts = await tg._download_document_attachments(message, context)
    assert len(atts) == 1
    assert atts[0].data == b"PDFDATA"
    assert atts[0].filename == "r.pdf"
    assert atts[0].mime == "application/pdf"


async def test_document_over_size_cap_is_placeholder():
    message = _doc_message(file_size=30 * 1024 * 1024)
    context = MagicMock()
    context.bot.get_file = AsyncMock()
    atts = await tg._download_document_attachments(message, context)
    assert atts[0].data is None and atts[0].note
    context.bot.get_file.assert_not_called()


async def test_document_download_failure_is_placeholder():
    message = _doc_message()
    context = MagicMock()
    context.bot.get_file = AsyncMock(side_effect=RuntimeError("net"))
    atts = await tg._download_document_attachments(message, context)
    assert atts[0].data is None and atts[0].note


async def test_no_document_returns_empty():
    message = MagicMock()
    message.document = None
    assert await tg._download_document_attachments(message, MagicMock()) == []


# ── Group 6: generated-image auto-upload (upload_func) ─────────────────────────


async def test_upload_func_sends_each_file(monkeypatch):
    sent = []

    async def fake_send_file_to(platform, connector, target, path, **kw):
        sent.append((platform, target, path))

    monkeypatch.setattr("fleetent.outbound.send_file_to", fake_send_file_to)
    upload = tg._make_upload_func(MagicMock(), chat_id="555", target_type="user", thread=None)
    await upload(["/tmp/a.png", "/tmp/b.png"])
    assert [s[2] for s in sent] == ["/tmp/a.png", "/tmp/b.png"]
    assert all(s[0] == "telegram" and s[1] == "555" for s in sent)


async def test_upload_func_swallows_single_failure(monkeypatch):
    async def fake_send_file_to(platform, connector, target, path, **kw):
        raise RuntimeError("upload boom")

    monkeypatch.setattr("fleetent.outbound.send_file_to", fake_send_file_to)
    upload = tg._make_upload_func(MagicMock(), chat_id="555", target_type="user", thread=None)
    await upload(["/tmp/a.png"])  # must not raise
