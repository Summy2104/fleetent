from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Telegram photos carry no explicit MIME; they are served as JPEG.
_TELEGRAM_PHOTO_MIME = "image/jpeg"

# Inbound non-image files larger than this are not downloaded (mirror Slack's cap): the agent
# reads files in its memory-bounded run_code container, so an over-cap file surfaces as a
# placeholder note instead of bytes.
_MAX_INBOUND_FILE_BYTES = 20 * 1024 * 1024


async def _send_reply(message: Any, text: str, approval: Any = None) -> None:
    """Send a Telegram reply, attaching an approval inline keyboard when an intent is given.

    Mirrors Slack's ``reply_func(text, approval=...)``: with no approval this is a plain text
    reply (behavior unchanged); with one it renders the neutral ``ApprovalPrompt`` into an
    inline keyboard so the requester-routed approval prompt carries buttons on Telegram too.
    """
    kwargs: dict[str, Any] = {}
    if approval is not None:
        from fleetent.outbound import render_approval_telegram

        kwargs["reply_markup"] = render_approval_telegram(approval)
    await message.reply_text(text, **kwargs)


async def _download_document_attachments(message: Any, context: Any) -> list[Any]:
    """Download an inbound Telegram document as a FileAttachment (mirror Slack non-image files).

    Over the size cap → ``data=None`` placeholder noting the limit (no download). A download
    failure → ``data=None`` placeholder noting the failure, logged, never raising. Images are
    NOT handled here (they keep the ``(bytes, mime)`` vision path).
    """
    from fleetent.im_gateway.normalizer import FileAttachment

    doc = getattr(message, "document", None)
    if doc is None:
        return []
    mime = getattr(doc, "mime_type", None) or "application/octet-stream"
    filename = getattr(doc, "file_name", None) or "file"
    size = getattr(doc, "file_size", 0) or 0
    if size > _MAX_INBOUND_FILE_BYTES:
        return [
            FileAttachment(
                data=None, mime=mime, filename=filename, note="超过大小上限，未下载"
            )
        ]
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as exc:  # noqa: BLE001 — best-effort; degrade to placeholder, never abort
        logger.warning("telegram_document_download_failed", filename=filename, error=str(exc))
        return [FileAttachment(data=None, mime=mime, filename=filename, note="文件接收失败")]
    return [FileAttachment(data=bytes(data), mime=mime, filename=filename)]


def _make_upload_func(
    bot: Any, *, chat_id: str, target_type: str, thread: Any
) -> Any:
    """Return an async callable that uploads generated files to the Telegram conversation.

    Converges onto the unified ``outbound.send_file_to`` primitive (mirror Slack); a single
    file's failure is swallowed so one bad upload never blocks the rest of the turn.
    """

    async def upload_func(paths: list[str]) -> None:
        from fleetent import outbound

        for path in paths:
            try:
                await outbound.send_file_to(
                    "telegram", bot, chat_id, path, target_type=target_type, thread=thread
                )
            except Exception as exc:  # noqa: BLE001 — best-effort, per-file isolation
                logger.warning("telegram_generated_upload_failed", path=path, error=str(exc))

    return upload_func


async def handle_approval_callback(update: Any, context: Any, agent_name: str) -> None:
    """Resolve a permission-gate approval from a Telegram inline-button click.

    Mirrors Slack's ``handle_approval_action``: the clicking user is the decision actor (gate
    authorization applies); on an accepted decision the prompt is rewritten to a result state
    (keyboard removed) and the suspended run is resumed. Reuses the platform-neutral approval
    components — no platform import. Only handles ``approval:`` callback data.
    """
    from fleetent.outbound import parse_approval_callback

    cq = getattr(update, "callback_query", None)
    if cq is None:
        return
    parsed = parse_approval_callback(getattr(cq, "data", None))
    if parsed is None:
        return
    decision_token, approval_id = parsed
    decision = "rejected" if decision_token == "reject" else "approved"
    always = decision_token == "approve_always"
    clicker = str(cq.from_user.id)

    from fleetent.governance import approval_store
    from fleetent.governance.approval_router import resolve_approval_request
    from fleetent.session import manager as session_mgr

    row = approval_store.get_approval(approval_id)
    session_id = str(row.get("session_id")) if row and row.get("session_id") else None
    authorized: set[str] | None = None
    if session_id:
        pending = await session_mgr.get_pending_approval(session_id, approval_id)
        if pending and pending.get("approver_ids"):
            authorized = {str(a) for a in pending["approver_ids"]}

    found = await resolve_approval_request(
        approval_id=approval_id,
        decision=decision,  # type: ignore[arg-type]
        approver_user_id=clicker,
        always=always,
        authorized_actors=authorized,
    )

    if not found:
        with contextlib.suppress(Exception):
            await cq.answer(
                text=f"⚠️ 无权审批 {approval_id}，或该请求已过期/已被处理。", show_alert=True
            )
        return

    with contextlib.suppress(Exception):
        await cq.answer()
    verdict = "✅ 已批准" if decision == "approved" else "❌ 已拒绝"
    suffix = "（始终允许）" if always else ""
    with contextlib.suppress(Exception):  # decision already took effect; edit is cosmetic
        await cq.message.edit_text(f"{verdict}{suffix} `{approval_id}` — by {clicker}")

    if session_id:
        from fleetent.im_gateway import normalizer
        from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext

        chat_id = str(cq.message.chat.id)

        async def _reply(text: str, approval: Any = None) -> None:
            await _send_reply(cq.message, text, approval=approval)

        resume_msg = NormalizedMessage(
            platform="telegram",
            session_id=session_id,
            user_id=clicker,
            text="",
            attachments=[],
            reply_func=_reply,
            agent_name=agent_name,
            session_context=SessionContext(platform="telegram", sender_id=clicker),
            outbound_connectors={"telegram": context.bot},
        )
        try:
            await normalizer._resume_pending_in_session(
                resume_msg, session_id, approval_id, decision
            )
        except Exception as exc:  # noqa: BLE001 — decision stands; resume is best-effort
            logger.warning(
                "telegram_approval_button_resume_failed", approval_id=approval_id, error=str(exc)
            )


async def _send_typing_for_progress(bot: Any, chat_id: str, evt: dict[str, Any]) -> None:
    """Re-arm Telegram's ~5s typing indicator for any progress event.

    im-progress-heartbeat: the typing action self-expires after ~5s, so it must be
    re-sent periodically — heartbeat events (emitted by the agent loop during long
    LLM calls / tools / sub_agent runs) drive exactly that. Event content is irrelevant
    (any progress event re-arms typing). Best-effort: a send failure is swallowed.
    """
    try:  # noqa: SIM105 — contextlib.suppress would obscure the awaited call
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:  # noqa: BLE001 — typing action is non-critical
        pass


async def _download_photo_attachments(message: Any, context: Any) -> list[tuple[bytes, str]]:
    """Download the largest PhotoSize of a Telegram message, if any.

    Best-effort: a download failure is logged and degrades to no attachments
    rather than aborting the message. The last PhotoSize is the highest
    resolution.
    """
    photos = getattr(message, "photo", None)
    if not photos:
        return []
    largest = photos[-1]
    try:
        tg_file = await context.bot.get_file(largest.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as exc:  # noqa: BLE001 — best-effort download, must not abort handler
        logger.warning("telegram_photo_download_failed", error=str(exc))
        return []
    return [(bytes(data), _TELEGRAM_PHOTO_MIME)]


def _derive_session_id(chat_type: str, user_id: int, reply_to_id: int | None) -> str:
    if chat_type == "private":
        return f"user:{user_id}"
    if reply_to_id is not None:
        return f"thread:{reply_to_id}"
    return f"user:{user_id}"


def create_app(agent_name: str, config: dict[str, Any]) -> object:
    """Create a python-telegram-bot Application bound to one agent's Telegram connection.

    The receiving connection identifies the agent (per-agent-telegram-connector): the
    handler stamps ``agent_name`` so routing skips channel→agent lookup. The connector
    identity is the owning agent name, passed through to the injected IM identity
    resolver; chat access is enforced by the access gate.
    """
    try:
        from telegram.ext import Application
    except ImportError:
        raise RuntimeError("python-telegram-bot not installed") from None

    bot_token = config.get("bot_token", "")
    builder = Application.builder().token(bot_token).concurrent_updates(True)
    application = builder.build()

    async def handle_message(update: object, context: object) -> None:
        from telegram import Update

        from fleetent.im_gateway.access import (  # noqa: PLC0415
            IMIdentityResolutionError,
            resolve_identity,
        )
        from fleetent.im_gateway.inbound_dispatch import dispatch  # noqa: PLC0415
        from fleetent.im_gateway.normalizer import (  # noqa: PLC0415
            NormalizedMessage,
            SessionContext,
        )
        from fleetent.outbound import ConversationAddress  # noqa: PLC0415

        assert isinstance(update, Update)
        if not update.message or not update.effective_user:
            return

        channel_id = str(update.message.chat.id)

        tg_user_id = update.effective_user.id
        # Identity is the platform-native id, resolved locally — no platform user_store.
        try:
            identity = resolve_identity("telegram", str(tg_user_id), agent_name)
        except IMIdentityResolutionError as exc:
            logger.warning(
                "telegram_identity_resolution_rejected",
                agent=agent_name,
                platform_user_id=str(tg_user_id),
                error=str(exc),
            )
            return

        reply_to = update.message.reply_to_message
        chat_type = update.message.chat.type

        session_id = _derive_session_id(
            chat_type=chat_type,
            user_id=tg_user_id,
            reply_to_id=reply_to.message_id if reply_to else None,
        )

        async def reply_func(text: str, approval: Any = None) -> None:
            await _send_reply(update.message, text, approval=approval)  # type: ignore[union-attr]

        async def progress_func(evt: dict) -> None:  # type: ignore[type-arg]
            await _send_typing_for_progress(context.bot, channel_id, evt)  # type: ignore[attr-defined]

        attachments = await _download_photo_attachments(update.message, context)
        attachments = list(attachments) + await _download_document_attachments(
            update.message, context
        )
        # Image messages carry their text in `caption`, not `text`.
        text = update.message.caption or update.message.text or ""
        upload_func = _make_upload_func(
            context.bot,  # type: ignore[attr-defined]
            chat_id=channel_id,
            target_type="user" if chat_type == "private" else "channel",
            thread=reply_to.message_id if reply_to else None,
        )

        msg = NormalizedMessage(
            platform="telegram",
            agent_name=agent_name,
            session_id=session_id,
            session_context=SessionContext(
                platform="telegram",
                sender_id=str(tg_user_id),
                sender_name=update.effective_user.full_name or "",
                chat_type="dm" if chat_type == "private" else "channel",
                channel_name=channel_id,
                was_mentioned=False,
                thread_root=str(reply_to.message_id) if reply_to else "",
            ),
            user_id=identity,
            text=text,
            attachments=attachments,
            reply_func=reply_func,
            progress_func=progress_func,
            upload_func=upload_func,
            channel_id=channel_id,
            outbound_connectors={"telegram": context.bot},
            conversation_address=ConversationAddress(
                platform="telegram",
                chat_id=channel_id,
                target_type="user",
                thread_id=None,
                user_id=str(tg_user_id),
                chat_type="dm" if chat_type == "private" else "channel",
                thread_root=str(reply_to.message_id) if reply_to else "",
            ),
        )
        await dispatch(msg)

    async def on_callback(update: object, context: object) -> None:
        await handle_approval_callback(update, context, agent_name)

    from telegram.ext import CallbackQueryHandler, MessageHandler, filters

    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
            handle_message,
        )
    )
    application.add_handler(CallbackQueryHandler(on_callback))
    return application


async def _run_polling(app: object) -> None:
    """Start polling and serve until cancelled (network seam)."""
    await app.initialize()  # type: ignore[attr-defined]
    await app.start()  # type: ignore[attr-defined]
    await app.updater.start_polling()  # type: ignore[attr-defined]
    # Polling runs in its own task; block here until the manager cancels us.
    await asyncio.Event().wait()


async def run(agent_name: str, config: dict[str, Any]) -> None:
    """Run one agent's Telegram connection until cancelled (network seam).

    Per-agent connection status is owned by the connector supervisor, which catches
    errors here and records them per agent. This runner just opens the connection.
    """
    from fleetent.im_gateway import connector_registry

    app = create_app(agent_name, config)
    # Register the live bot so the cron scheduler can deliver fired-task replies to this
    # agent's Telegram at fire time (resolved per fire, cleared on disconnect).
    bot = getattr(app, "bot", None)
    if bot is not None:
        connector_registry.register("telegram", agent_name, bot)
    try:
        await _run_polling(app)
    finally:
        connector_registry.unregister("telegram", agent_name)
