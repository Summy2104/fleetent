from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_IMAGE_MIME_PREFIX = "image/"


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
    per-agent-im-access). ``config.channels``, when non-empty, filters which channels
    the agent responds in.
    """
    try:
        from slack_bolt.async_app import AsyncApp
    except ImportError:
        raise RuntimeError("slack-bolt not installed") from None

    bot_token = config.get("bot_token", "")
    channels = config.get("channels") or []
    app = AsyncApp(token=bot_token)

    @app.event("message")
    async def handle_message(event: dict[str, Any], say: object) -> None:
        from fleetent.im_gateway.normalizer import NormalizedMessage, route
        from fleetent.im_user_store import get_or_create

        channel = event.get("channel") or ""
        if channels and channel not in channels:
            return  # channel outside this agent's response filter

        slack_user_id = event.get("user") or "unknown"
        user = get_or_create(owner_id, "slack", slack_user_id)
        thread_ts = event.get("thread_ts")
        channel_type = event.get("channel_type") or "channel"

        session_id = _derive_session_id(
            user_id=slack_user_id,
            channel_type=channel_type,
            thread_ts=thread_ts,
        )

        reply_thread = thread_ts or event.get("ts")

        async def reply_func(text: str) -> None:
            await say(text=text, thread_ts=reply_thread)  # type: ignore[operator]

        files = event.get("files") or []
        attachments = await _download_image_attachments(list(files), bot_token)

        msg = NormalizedMessage(
            platform="slack",
            owner_id=owner_id,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user.id,
            text=event.get("text") or "",
            attachments=attachments,
            reply_func=reply_func,
            channel_id=channel,
        )
        await route(msg)

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
