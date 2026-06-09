from __future__ import annotations

import contextlib
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_IMAGE_MIME_PREFIX = "image/"

# Human-readable status labels for common tool names shown in the Slack
# Assistants API status indicator while the agent is running.
_TOOL_STATUS: dict[str, str] = {
    # Google Workspace
    "google-workspace__manage_drive": "📂 正在操作 Google Drive",
    "google-workspace__manage_email": "📧 正在处理邮件",
    "google-workspace__manage_calendar": "📅 正在查询日历",
    "google-workspace__manage_docs": "📄 正在处理文档",
    "google-workspace__manage_sheets": "📊 正在处理表格",
    "google-workspace__manage_meet": "🎥 正在查询会议",
    "google-workspace__manage_tasks": "✅ 正在处理任务",
    "google-workspace__manage_accounts": "👤 正在管理账号",
    "google-workspace__manage_scratchpad": "📝 正在编辑草稿",
    "google-workspace__queue_operations": "⚙️ 正在批量处理",
    # Built-ins
    "run_code": "💻 正在执行代码",
    "web_search": "🔍 正在搜索网页",
    "read_file": "📖 正在读取文件",
    "write_file": "✍️ 正在写入文件",
    "generate_image": "🎨 正在生成图片",
    "analyze_image": "🔍 正在分析图片",
}


def _tool_status_text(tool_name: str) -> str:
    """Return a human-readable status string for the given tool name."""
    if tool_name in _TOOL_STATUS:
        return _TOOL_STATUS[tool_name] + "..."
    # Prefix match (e.g. custom MCP servers)
    for prefix, label in _TOOL_STATUS.items():
        if tool_name.startswith(prefix):
            return label + "..."
    # Generic fallback: strip namespace, replace underscores
    short = tool_name.split("__")[-1].replace("_", " ")
    return f"🔧 {short}..."


async def _make_status_funcs(
    client: Any,
    channel: str,
    reply_thread: str | None,
    say: Any,
) -> tuple[Any, Any]:
    """Set the initial Assistants API status and return ``(reply_func, progress_func)``.

    Uses the native ``assistant_threads_setStatus`` indicator (shown below the bot name,
    no extra thread message). If the App has not enabled Agents & Assistants, the first
    call fails and both returned funcs degrade gracefully — ``progress_func`` becomes a
    no-op and ``reply_func`` still delivers the final answer via ``say()``.
    """
    status_ok = False
    try:
        await client.assistant_threads_setStatus(
            channel_id=channel,
            thread_ts=reply_thread,
            status="🤔 思考中...",
        )
        status_ok = True
    except Exception as exc:  # noqa: BLE001 — feature may be disabled; degrade, don't abort
        logger.warning("slack_assistant_status_failed", channel=channel, error=str(exc))

    async def reply_func(text: str) -> None:
        if status_ok:
            with contextlib.suppress(Exception):
                await client.assistant_threads_setStatus(
                    channel_id=channel, thread_ts=reply_thread, status=""
                )
        if say is not None:
            await say(text=text, thread_ts=reply_thread)

    async def progress_func(evt: dict[str, Any]) -> None:
        if not status_ok:
            return
        tool_name = evt.get("name", "tool")
        try:
            await client.assistant_threads_setStatus(
                channel_id=channel,
                thread_ts=reply_thread,
                status=_tool_status_text(tool_name),
            )
        except Exception as exc:  # noqa: BLE001 — status update failure must not break the run
            logger.warning("slack_progress_status_failed", tool=tool_name, error=str(exc))

    return reply_func, progress_func


def _make_upload_func(
    client: Any,
    channel: str,
    reply_thread: str | None,
) -> Any:
    """Return an async callable that uploads a list of local image paths to Slack.

    Wraps ``files_upload_v2``; single-file failures are logged and skipped so
    that one bad upload never prevents the rest from going through.
    """

    async def upload_func(paths: list[str]) -> None:
        for path in paths:
            try:
                await client.files_upload_v2(
                    channel=channel,
                    thread_ts=reply_thread,
                    file=path,
                )
            except Exception as exc:  # noqa: BLE001 — upload failure must not break the response
                logger.warning("slack_image_upload_failed", path=path, error=str(exc))

    return upload_func


async def _download_image_attachments(
    files: list[dict[str, Any]], bot_token: str
) -> list[tuple[bytes, str]]:
    """Download `image/*` Slack files via their authenticated `url_private`.

    Best-effort: a file that fails to download is logged and skipped rather than
    aborting the whole message. Non-image files are ignored.
    """
    import httpx

    attachments: list[tuple[bytes, str]] = []
    headers = {"Authorization": f"Bearer {bot_token}"}
    async with httpx.AsyncClient() as client:
        for f in files:
            mime = f.get("mimetype") or ""
            url = f.get("url_private")
            if not mime.startswith(_IMAGE_MIME_PREFIX) or not url:
                continue
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("slack_image_download_failed", url=url, error=str(exc))
                continue
            attachments.append((resp.content, mime))
    return attachments


def _derive_session_id(user_id: str, channel_type: str, thread_ts: str | None) -> str:
    if channel_type == "im":
        return f"user:{user_id}"
    if thread_ts:
        return f"thread:{thread_ts}"
    # Channel message without thread: use user as session (bot will reply in thread)
    return f"user:{user_id}"


def create_app(agent_name: str, owner_id: str, config: dict[str, Any]) -> object:
    """Create a slack-bolt AsyncApp bound to one agent's Slack connection.

    The receiving connection identifies the agent (per-agent-slack-connector): the
    handler stamps ``agent_name`` so routing skips channel→agent lookup. ``owner_id``
    still scopes user mapping / allowlist (per-agent isolation of those is deferred to
    per-agent-im-access). Channel access is enforced by the normalizer access gate,
    not this handler.
    """
    try:
        from slack_bolt.async_app import AsyncApp
    except ImportError:
        raise RuntimeError("slack-bolt not installed") from None

    bot_token = config.get("bot_token", "")
    app = AsyncApp(token=bot_token)

    async def _handle(event: dict[str, Any], client: Any, say: Any = None) -> None:
        from fleetent.im_gateway.access import resolve_identity
        from fleetent.im_gateway.normalizer import NormalizedMessage, route

        channel = event.get("channel") or ""
        slack_user_id = event.get("user") or "unknown"
        # Identity is the platform-native id, resolved locally — no platform user_store.
        identity = resolve_identity("slack", slack_user_id)
        thread_ts = event.get("thread_ts")
        channel_type = event.get("channel_type") or "channel"

        session_id = _derive_session_id(
            user_id=slack_user_id,
            channel_type=channel_type,
            thread_ts=thread_ts,
        )

        reply_thread = thread_ts or event.get("ts")

        # Native Assistants API status indicator (shows below the bot name, no extra
        # thread message). Degrades to a plain say() reply if the feature is disabled.
        reply_func, progress_func = await _make_status_funcs(client, channel, reply_thread, say)

        files = event.get("files") or []
        attachments = await _download_image_attachments(list(files), bot_token)

        msg = NormalizedMessage(
            platform="slack",
            owner_id=owner_id,
            agent_name=agent_name,
            session_id=session_id,
            user_id=identity,
            text=event.get("text") or "",
            attachments=attachments,
            reply_func=reply_func,
            progress_func=progress_func,
            channel_id=channel,
            upload_func=_make_upload_func(client, channel, reply_thread),
        )
        await route(msg)

    @app.event("app_mention")
    async def handle_mention(event: dict[str, Any], client: Any, say: Any = None) -> None:
        """Handle @mention in channels."""
        await _handle(event, client, say)

    @app.event("message")
    async def handle_dm(event: dict[str, Any], client: Any, say: Any = None) -> None:
        """Handle DMs only; channel messages are handled via app_mention."""
        if (event.get("channel_type") or "") == "im":
            await _handle(event, client, say)

    return app


async def _run_socket_mode(app: object, app_token: str) -> None:
    """Open the Socket Mode connection and serve until cancelled (network seam)."""
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    handler = AsyncSocketModeHandler(app, app_token)  # type: ignore[arg-type]
    await handler.start_async()  # type: ignore[no-untyped-call]


async def run(agent_name: str, owner_id: str, config: dict[str, Any]) -> None:
    """Run one agent's Slack connection until cancelled (network seam).

    Per-agent connection status is owned by the connector supervisor, which catches
    errors here and records them per agent. This runner just opens the connection.
    """
    app = create_app(agent_name, owner_id, config)
    await _run_socket_mode(app, config.get("app_token", ""))
