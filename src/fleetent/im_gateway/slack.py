from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_IMAGE_MIME_PREFIX = "image/"
_PROGRESS_THROTTLE_SECONDS = 1.0


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

        # Attempt to post a placeholder message immediately so the user sees activity.
        # On success, both reply_func and progress_func update this message in-place.
        # On failure, fall back to the original say()-based reply with no progress.
        placeholder_ts: str | None = None
        try:
            resp = await client.chat_postMessage(
                channel=channel,
                text="🤔 思考中…",
                thread_ts=reply_thread,
            )
            if isinstance(resp, dict):
                placeholder_ts = resp.get("ts")
        except Exception as exc:  # noqa: BLE001 — placeholder failure must not abort handler
            logger.warning("slack_placeholder_failed", error=str(exc))

        if placeholder_ts is not None:
            _placeholder_ts = placeholder_ts  # captured for closures

            async def reply_func(text: str) -> None:
                await client.chat_update(channel=channel, ts=_placeholder_ts, text=text)

            last_update: list[float] = [0.0]

            async def progress_func(evt: dict[str, Any]) -> None:
                now = time.monotonic()
                if now - last_update[0] < _PROGRESS_THROTTLE_SECONDS:
                    return
                last_update[0] = now
                tool_name = evt.get("name", "tool")
                try:
                    await client.chat_update(
                        channel=channel,
                        ts=_placeholder_ts,
                        text=f"🔧 正在调用 {tool_name}…",
                    )
                except Exception as exc:  # noqa: BLE001 — progress update failure is non-critical
                    logger.debug("slack_progress_update_failed", error=str(exc))

        else:
            # Degraded path: no placeholder — use say() for the final reply, no progress.
            async def reply_func(text: str) -> None:  # noqa: F811
                if say is not None:
                    await say(text=text, thread_ts=reply_thread)

            progress_func = None  # type: ignore[assignment]

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
