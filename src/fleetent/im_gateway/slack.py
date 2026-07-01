from __future__ import annotations

import contextlib
import re
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


# Max distinct tool labels shown in one aggregated status before collapsing to a count.
_MAX_STATUS_TOOLS = 3


def _tool_label(tool_name: str) -> str:
    """Return the bare human-readable label for a tool name (no trailing ellipsis)."""
    if tool_name in _TOOL_STATUS:
        return _TOOL_STATUS[tool_name]
    # Prefix match (e.g. custom MCP servers)
    for prefix, label in _TOOL_STATUS.items():
        if tool_name.startswith(prefix):
            return label
    # Generic fallback: strip namespace, replace underscores
    short = tool_name.split("__")[-1].replace("_", " ")
    return f"🔧 {short}"


def _tool_status_text(tool_name: str) -> str:
    """Return a human-readable status string for a single tool name."""
    return _tool_label(tool_name) + "..."


def _aggregate_status_text(names: list[str]) -> str:
    """Compose one status line covering all in-flight tools of a batch.

    A turn may dispatch several tools in parallel; showing only one would hide the
    rest. Labels are joined; beyond `_MAX_STATUS_TOOLS` the line collapses to a count
    so it never grows unbounded.
    """
    if not names:
        return "🤔 思考中..."
    labels = [_tool_label(n) for n in names[:_MAX_STATUS_TOOLS]]
    text = " · ".join(labels)
    if len(names) > _MAX_STATUS_TOOLS:
        text += f" 等 {len(names)} 项"
    return text + "..."


def _status_text_for_event(evt: dict[str, Any]) -> str:
    """Map a progress event to an aggregated status line.

    Accepts the batch shape `{"names": [...]}` and falls back to the legacy
    single-tool `{"name": ...}` for backward compatibility.
    """
    names = evt.get("names")
    if not names:
        single = evt.get("name")
        names = [single] if single else []
    return _aggregate_status_text(list(names))


_THINKING_STATUS = "🤔 思考中..."


def _loading_messages_for_event(evt: dict[str, Any]) -> list[str]:
    """Per-tool rotation messages for the assistant message area.

    Slack rotates these while the agent works; supplying our own keeps the rotation
    showing fleetent's tool labels instead of Slack's built-in default placeholders.
    """
    names = evt.get("names")
    if not names:
        single = evt.get("name")
        names = [single] if single else []
    if not names:
        return [_THINKING_STATUS]
    return [_tool_status_text(n) for n in names]


class _SlackStatusKeeper:
    """Per-run status state so heartbeats keep the indicator alive without clobbering it.

    im-progress-heartbeat: a `tool_call` event sets the current label/loading messages;
    a `heartbeat` event re-asserts the last label with `· 已 Ns` appended (keepalive +
    liveness) instead of resetting to a generic placeholder. The two event kinds never
    clear each other.
    """

    def __init__(self) -> None:
        self._label = _THINKING_STATUS
        self._loading = [_THINKING_STATUS]

    def text_and_loading(self, evt: dict[str, Any]) -> tuple[str, list[str]]:
        if evt.get("type") == "heartbeat":
            elapsed = int(evt.get("elapsed_s", 0))
            return f"{self._label} · 已 {elapsed}s", self._loading
        self._label = _status_text_for_event(evt)
        self._loading = _loading_messages_for_event(evt)
        return self._label, self._loading


def _has_postable_content(text: str, blocks: list[dict[str, Any]] | None) -> bool:
    """Whether a reply has content Slack will accept.

    Slack rejects ``chat.postMessage`` with empty text and no blocks (``no_text``), which
    bubbles a SlackApiError into the bolt listener and breaks reply/approval delivery. A
    reply with neither (an empty agent turn) is skipped rather than posted.
    """
    return bool((text or "").strip()) or bool(blocks)


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
            status=_THINKING_STATUS,
            loading_messages=[_THINKING_STATUS],
        )
        status_ok = True
    except Exception as exc:  # noqa: BLE001 — feature may be disabled; degrade, don't abort
        logger.warning("slack_assistant_status_failed", channel=channel, error=str(exc))

    async def reply_func(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
        if status_ok:
            with contextlib.suppress(Exception):
                await client.assistant_threads_setStatus(
                    channel_id=channel, thread_ts=reply_thread, status=""
                )
        if say is not None and _has_postable_content(text, blocks):
            kwargs: dict[str, Any] = {"text": text, "thread_ts": reply_thread}
            if blocks is not None:
                kwargs["blocks"] = blocks
            await say(**kwargs)

    keeper = _SlackStatusKeeper()

    async def progress_func(evt: dict[str, Any]) -> None:
        if not status_ok:
            return
        status, loading = keeper.text_and_loading(evt)
        try:
            await client.assistant_threads_setStatus(
                channel_id=channel,
                thread_ts=reply_thread,
                status=status,
                loading_messages=loading,
            )
        except Exception as exc:  # noqa: BLE001 — status update failure must not break the run
            logger.warning("slack_progress_status_failed", error=str(exc))

    return reply_func, progress_func


async def handle_approval_action(
    ack: Any, body: Any, client: Any, agent_name: str | None = None
) -> None:
    """Resolve a permission-gate approval from a Block Kit button click.

    The clicking user's Slack id (interaction payload) is the decision actor, so
    the gate's authorization check applies — a bystander's click is rejected with
    an ephemeral notice while the prompt keeps its buttons. On an accepted
    decision the prompt message is rewritten to a result state (buttons removed)
    to prevent double-clicks, then the suspended run is resumed (approval-suspend-resume).

    managed-approval-button-wire-statedb (AAA-8204 #2): under node-managed placement the
    slack edge runs in the node process, which never wired approval_store/state_db — so
    resolving in place raises ``state_db not initialized`` and the run never resumes. When a
    node injected its inbound dispatcher we instead synthesize the equivalent approve/reject
    command and forward it through that dispatcher to the agent process (which owns
    approval_store/session/connectors), reusing the text-command resume path. Standalone
    (agent self-hosted, no dispatcher injected) keeps resolving + resuming in place.
    """
    from fleetent.governance import approval_store
    from fleetent.governance.approval_router import resolve_approval_request
    from fleetent.im_gateway import inbound_dispatch
    from fleetent.session import manager as session_mgr

    await ack()
    action = (body.get("actions") or [{}])[0]
    action_id = action.get("action_id", "")
    approval_id = action.get("value", "")
    clicker = (body.get("user") or {}).get("id", "")
    channel = (body.get("channel") or {}).get("id", "")
    message_ts = (body.get("message") or {}).get("ts", "")

    decision = "rejected" if action_id == "approval_reject" else "approved"
    always = action_id == "approval_approve_always"

    forwarder = inbound_dispatch.get_inbound_dispatcher()
    if forwarder is not None:
        await _forward_approval_decision(
            forwarder,
            client,
            channel=channel,
            message_ts=message_ts,
            agent_name=agent_name,
            clicker=clicker,
            approval_id=approval_id,
            decision=decision,
            always=always,
        )
        return

    # The run persisted the approval's session id; recover authorized actors from that
    # session's pending entry so authorization survives a restart.
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
            await client.chat_postEphemeral(
                channel=channel,
                user=clicker,
                text=f"⚠️ 无权审批 `{approval_id}`，或该请求已过期/已被处理。",
            )
        return

    verdict = "✅ 已批准" if decision == "approved" else "❌ 已拒绝"
    suffix = "（始终允许）" if always else ""
    with contextlib.suppress(Exception):  # decision already took effect; update is cosmetic
        await client.chat_update(
            channel=channel,
            ts=message_ts,
            text=f"{verdict}{suffix} `{approval_id}` — by <@{clicker}>",
            blocks=[],
        )

    # Resume the suspended run via the same path the text command uses. Best-effort:
    # a resume failure must not undo the already-recorded decision.
    if session_id and agent_name:
        from fleetent.im_gateway import normalizer
        from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext

        async def _reply(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
            if not _has_postable_content(text, blocks):
                return
            kwargs: dict[str, Any] = {"channel": channel, "text": text}
            if blocks is not None:
                kwargs["blocks"] = blocks
            await client.chat_postMessage(**kwargs)

        resume_msg = NormalizedMessage(
            platform="slack",
            session_id=session_id,
            user_id=clicker,
            text="",
            attachments=[],
            reply_func=_reply,
            agent_name=agent_name,
            session_context=SessionContext(platform="slack", sender_id=clicker),
            outbound_connectors={"slack": client},
        )
        try:
            # _resume_pending_in_session delivers the final reply to the persisted address
            # itself; re-posting here (`_reply` targets the button's channel top-level) would
            # land it in the wrong place.
            await normalizer._resume_pending_in_session(
                resume_msg, session_id, approval_id, decision
            )
        except Exception as exc:  # noqa: BLE001 — decision stands; resume is best-effort
            logger.warning("approval_button_resume_failed", approval_id=approval_id, error=str(exc))


async def _forward_approval_decision(
    forwarder: Any,
    client: Any,
    *,
    channel: str,
    message_ts: str,
    agent_name: str | None,
    clicker: str,
    approval_id: str,
    decision: str,
    always: bool,
) -> None:
    """Managed mode (AAA-8204 #2): forward the button decision as a synthesized text command.

    The node process can neither read the approval store nor resume the run (no state_db),
    so the click becomes an ``approve/reject [always] <id>`` command dispatched to the agent
    process via the injected inbound dispatcher — the same chain a typed approval takes. The
    agent owns authorization + resume + (managed) connector resolution.

    AAA-8204 #2 patch: the requester is stored as an internal identity (uuid); the click
    carries the raw Slack user id. Resolve it via ``resolve_identity`` first — exactly like
    the inbound path (slack.py) — so the agent's authorization compares like ids (a raw Slack
    id would never match the resolved requester → ``approval_unauthorized_actor``).
    """
    from fleetent.im_gateway.access import IMIdentityResolutionError, resolve_identity
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext

    try:
        clicker_identity = resolve_identity("slack", clicker, agent_name or "default")
    except IMIdentityResolutionError as exc:
        logger.warning("approval_button_identity_unresolved", clicker=clicker, error=str(exc))
        with contextlib.suppress(Exception):
            await client.chat_postEphemeral(
                channel=channel, user=clicker, text="⚠️ 无法识别你的身份，请重试。"
            )
        return

    verb = "approve" if decision == "approved" else "reject"
    command = (
        f"{verb} always {approval_id}"
        if always and decision == "approved"
        else f"{verb} {approval_id}"
    )

    # AAA-8204 #2 patch (b): authorization is decided asynchronously in the agent (method A),
    # so node cannot know yet whether the decision took effect — it must NOT optimistically
    # claim "已批准" (that contradicts a later unauthorized notice). Move the prompt off its
    # buttons (no double-click) to a neutral in-progress state; the agent delivers the real
    # outcome — the resumed run's result on success, an unauthorized/expired notice on failure.
    with contextlib.suppress(Exception):  # cosmetic; the agent owns the authoritative result
        await client.chat_update(
            channel=channel,
            ts=message_ts,
            text=f"⏳ 已提交审批 `{approval_id}` — by <@{clicker}>，正在处理…",
            blocks=[],
        )

    async def _reply(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
        # Used only for route()'s direct notices (e.g. unauthorized/expired); the resumed
        # run's final reply is delivered to the persisted address by _resume_pending_in_session.
        if not _has_postable_content(text, blocks):
            return
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        await client.chat_postMessage(**kwargs)

    msg = NormalizedMessage(
        platform="slack",
        # The agent resolves the run's real session from the approval row (like the text
        # path); this is only a fallback id for that lookup.
        session_id=f"slack:dm:{clicker}:approval-{approval_id}",
        user_id=clicker_identity,
        text=command,
        attachments=[],
        reply_func=_reply,
        channel_id=channel,
        agent_name=agent_name or "",
        session_context=SessionContext(platform="slack", sender_id=clicker),
        outbound_connectors={"slack": client},
    )
    await forwarder(msg)


def _make_upload_func(
    client: Any,
    channel: str,
    reply_thread: str | None,
) -> Any:
    """Return an async callable that uploads a list of local image paths to Slack.

    Converges onto the unified ``outbound.send_file_to`` primitive (single delivery
    implementation shared with the ``send_file`` tool); the inbound ``channel`` is the
    delivery target, so the channel (not user-DM) path is used directly. Single-file
    failures are swallowed by the primitive so one bad upload never blocks the rest.
    """
    from fleetent import outbound

    async def upload_func(paths: list[str]) -> None:
        for path in paths:
            await outbound.send_file_to(
                "slack", client, channel, path, target_type="channel", thread=reply_thread
            )

    return upload_func


# Inbound non-image files larger than this are not downloaded: run_code's container
# is memory-bounded and the agent reads files there. Over-cap files surface as a
# placeholder note rather than being silently dropped.
_MAX_FILE_BYTES = 20 * 1024 * 1024


def _is_html_response(resp: Any) -> bool:
    """True when a download response is an HTML page rather than file bytes.

    Slack serves a sign-in / error HTML page (not the file) when the bot token lacks the
    required scope or has no access to the file; treating that HTML as file bytes would
    poison downstream tools, so callers degrade instead.
    """
    ctype = resp.headers.get("content-type", "") if hasattr(resp, "headers") else ""
    return ctype.split(";")[0].strip().lower() == "text/html"


async def _download_attachments(files: list[dict[str, Any]], bot_token: str) -> list[Any]:
    """Download inbound Slack files for the agent (im-file-attachment).

    `image/*` files are downloaded into `(bytes, mime)` tuples (the vision path,
    unchanged). Non-image files are downloaded into `FileAttachment` items; an
    over-cap or failed download degrades to a `data=None` placeholder carrying a
    note, never raising. Shared by all three receive paths so one fix covers them.
    """
    import httpx

    from fleetent.im_gateway.normalizer import FileAttachment

    out: list[Any] = []
    headers = {"Authorization": f"Bearer {bot_token}"}
    cap_mb = _MAX_FILE_BYTES // (1024 * 1024)
    over_cap_note = f"超过大小上限（{cap_mb} MB）"
    # follow_redirects: Slack serves some file types (e.g. PDF) via a 302 from
    # files.slack.com to the slack-files.com sandbox domain; the policy is undocumented
    # and may apply to any type, so we follow unconditionally rather than special-casing.
    # The redirect target is cross-origin, so httpx strips the Authorization header — safe,
    # since that URL carries its own signed token.
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for f in files:
            mime = f.get("mimetype") or ""
            url = f.get("url_private")
            if not url:
                continue
            if mime.startswith(_IMAGE_MIME_PREFIX):
                try:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("slack_image_download_failed", url=url, error=str(exc))
                    continue
                if _is_html_response(resp):
                    logger.warning(
                        "slack_image_download_failed",
                        url=url,
                        error="content-type=text/html (check bot token scopes / file access)",
                    )
                    continue
                out.append((resp.content, mime))
                continue
            filename = f.get("name") or f.get("title") or "file"
            size = f.get("size")
            if isinstance(size, int) and size > _MAX_FILE_BYTES:
                logger.warning("slack_file_too_large", filename=filename, size=size)
                out.append(
                    FileAttachment(data=None, mime=mime, filename=filename, note=over_cap_note)
                )
                continue
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "slack_file_download_failed", url=url, filename=filename, error=str(exc)
                )
                out.append(
                    FileAttachment(data=None, mime=mime, filename=filename, note="文件下载失败")
                )
                continue
            if _is_html_response(resp):
                logger.warning(
                    "slack_file_download_failed",
                    url=url,
                    filename=filename,
                    error="content-type=text/html (check bot token scopes / file access)",
                )
                out.append(
                    FileAttachment(data=None, mime=mime, filename=filename, note="文件下载失败")
                )
                continue
            content = resp.content
            if len(content) > _MAX_FILE_BYTES:
                logger.warning("slack_file_too_large", filename=filename, size=len(content))
                out.append(
                    FileAttachment(data=None, mime=mime, filename=filename, note=over_cap_note)
                )
                continue
            out.append(FileAttachment(data=content, mime=mime, filename=filename))
    return out


def _derive_session_id(
    *, channel_type: str, channel_id: str, user_id: str, thread_root: str
) -> str:
    """Thread-first session id keyed by the thread the bot replies into.

    ``thread_root`` is ``thread_ts or the message's own ts`` — a top-level message
    (the bot threads on it) and its follow-ups inside that thread therefore share one
    session. DMs are namespaced per user, channels per channel, so the two never
    collide; each new top-level message / assistant-pane conversation is a new session.
    """
    if channel_type == "im":
        return f"slack:dm:{user_id}:{thread_root}"
    return f"slack:thread:{channel_id}:{thread_root}"


async def _route_assistant_message(
    *,
    payload: dict[str, Any],
    context: Any,
    set_status: Any,
    say: Any,
    client: Any,
    agent_name: str,
    bot_token: str,
) -> None:
    """Route one Assistant-thread user message through the agent pipeline.

    ``set_status`` and ``say`` are provided by slack-bolt's Assistant middleware,
    already bound to the **assistant thread** — so the status indicator renders in
    the Assistant pane (the prior bug used the message's own ts). ``reply_func`` /
    ``progress_func`` close over them; ``progress_func`` aggregates the whole tool
    batch so multi-tool turns show every in-flight tool, not only the last.
    """
    from fleetent.im_gateway.access import IMIdentityResolutionError, resolve_identity
    from fleetent.im_gateway.inbound_dispatch import dispatch
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
    from fleetent.outbound import ConversationAddress

    channel = getattr(context, "channel_id", None) or payload.get("channel") or ""
    thread_ts = getattr(context, "thread_ts", None)
    slack_user_id = payload.get("user") or getattr(context, "user_id", None) or "unknown"
    try:
        identity = resolve_identity("slack", slack_user_id, agent_name)
    except IMIdentityResolutionError as exc:
        logger.warning(
            "slack_identity_resolution_rejected",
            agent=agent_name,
            platform_user_id=slack_user_id,
            error=str(exc),
        )
        return

    with contextlib.suppress(Exception):
        await set_status(_THINKING_STATUS, loading_messages=[_THINKING_STATUS])

    async def reply_func(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
        with contextlib.suppress(Exception):
            await set_status("")
        if not _has_postable_content(text, blocks):
            return
        if blocks is not None:
            await say(text=text, blocks=blocks)
        else:
            await say(text)

    keeper = _SlackStatusKeeper()

    async def progress_func(evt: dict[str, Any]) -> None:
        status, loading = keeper.text_and_loading(evt)
        try:
            await set_status(status, loading_messages=loading)
        except Exception as exc:  # noqa: BLE001 — status update failure must not break the run
            logger.warning("slack_progress_status_failed", error=str(exc))

    files = payload.get("files") or []
    attachments = await _download_attachments(list(files), bot_token)

    msg = NormalizedMessage(
        platform="slack",
        agent_name=agent_name,
        session_id=_derive_session_id(
            channel_type="im",
            channel_id=channel,
            user_id=slack_user_id,
            thread_root=thread_ts or payload.get("ts") or slack_user_id,
        ),
        session_context=SessionContext(
            platform="slack",
            sender_id=slack_user_id,
            sender_name=(payload.get("user_profile") or {}).get("display_name") or "",
            chat_type="dm",
            channel_name=channel,
            was_mentioned=False,
            thread_root=thread_ts or payload.get("ts") or "",
        ),
        user_id=identity,
        text=payload.get("text") or "",
        attachments=attachments,
        reply_func=reply_func,
        progress_func=progress_func,
        channel_id=channel,
        upload_func=_make_upload_func(client, channel, thread_ts),
        outbound_connectors={"slack": client},
        conversation_address=ConversationAddress(
            platform="slack",
            chat_id=channel,
            target_type="channel",
            thread_id=thread_ts or payload.get("ts"),
            user_id=slack_user_id,
            chat_type="dm",
            thread_root=thread_ts or payload.get("ts") or "",
        ),
    )
    await dispatch(msg)


def create_app(agent_name: str, config: dict[str, Any]) -> object:
    """Create a slack-bolt AsyncApp bound to one agent's Slack connection.

    The receiving connection identifies the agent (per-agent-slack-connector): the
    handler stamps ``agent_name`` so routing skips channel→agent lookup. Channel access
    is enforced by the normalizer access gate, not this handler. The connector identity
    is the owning agent name, passed through to the injected IM identity resolver.

    DM / assistant-pane conversations are handled by the Assistant container so the
    native status indicator binds to the real assistant thread; ``app_mention`` keeps
    the channel path, and a fallback ``message`` (im) listener still serves plain DMs
    when the app has not enabled Agents & Assistants (the Assistant middleware passes
    non-assistant messages through via ``next()``).
    """
    try:
        from slack_bolt.async_app import AsyncApp, AsyncAssistant
    except ImportError:
        raise RuntimeError("slack-bolt not installed") from None

    bot_token = config.get("bot_token", "")
    app = AsyncApp(token=bot_token)

    # Approval button clicks (requires Interactivity enabled on the Slack App;
    # Socket Mode delivers block_actions over the existing connection). The agent name
    # is threaded so the handler can resume the suspended run on this connector's agent.
    async def _on_approval_action(ack: Any, body: Any, client: Any) -> None:
        await handle_approval_action(ack, body, client, agent_name=agent_name)

    app.action(re.compile(r"^approval_"))(_on_approval_action)

    assistant = AsyncAssistant()

    @assistant.thread_started
    async def _assistant_thread_started(say: Any = None) -> None:
        """Assistant pane opened; status is set when a message actually arrives."""
        return

    @assistant.user_message
    async def _assistant_user_message(
        payload: dict[str, Any],
        context: Any,
        set_status: Any,
        say: Any,
        client: Any,
    ) -> None:
        await _route_assistant_message(
            payload=payload,
            context=context,
            set_status=set_status,
            say=say,
            client=client,
            agent_name=agent_name,
            bot_token=bot_token,
        )

    app.assistant(assistant)

    async def _handle(event: dict[str, Any], client: Any, say: Any = None) -> None:
        from fleetent.im_gateway.access import IMIdentityResolutionError, resolve_identity
        from fleetent.im_gateway.inbound_dispatch import dispatch
        from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
        from fleetent.outbound import ConversationAddress

        channel = event.get("channel") or ""
        slack_user_id = event.get("user") or "unknown"
        # Identity is the platform-native id, resolved locally — no platform user_store.
        try:
            identity = resolve_identity("slack", slack_user_id, agent_name)
        except IMIdentityResolutionError as exc:
            logger.warning(
                "slack_identity_resolution_rejected",
                agent=agent_name,
                platform_user_id=slack_user_id,
                error=str(exc),
            )
            return
        thread_ts = event.get("thread_ts")
        channel_type = event.get("channel_type") or "channel"

        reply_thread = thread_ts or event.get("ts")
        session_id = _derive_session_id(
            channel_type=channel_type,
            channel_id=channel,
            user_id=slack_user_id,
            thread_root=reply_thread or slack_user_id,
        )

        # Native Assistants API status indicator (shows below the bot name, no extra
        # thread message). Degrades to a plain say() reply if the feature is disabled.
        reply_func, progress_func = await _make_status_funcs(client, channel, reply_thread, say)

        files = event.get("files") or []
        attachments = await _download_attachments(list(files), bot_token)

        msg = NormalizedMessage(
            platform="slack",
            agent_name=agent_name,
            session_id=session_id,
            session_context=SessionContext(
                platform="slack",
                sender_id=slack_user_id,
                sender_name=(event.get("user_profile") or {}).get("display_name") or "",
                chat_type="dm" if channel_type == "im" else "channel",
                channel_name=channel,
                was_mentioned=channel_type != "im",
                thread_root=reply_thread or "",
            ),
            user_id=identity,
            text=event.get("text") or "",
            attachments=attachments,
            reply_func=reply_func,
            progress_func=progress_func,
            channel_id=channel,
            upload_func=_make_upload_func(client, channel, reply_thread),
            outbound_connectors={"slack": client},
            conversation_address=ConversationAddress(
                platform="slack",
                chat_id=channel,
                target_type="channel",
                thread_id=reply_thread,
                user_id=slack_user_id,
                chat_type="dm" if channel_type == "im" else "channel",
                thread_root=reply_thread or "",
            ),
        )
        await dispatch(msg)

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


async def run(agent_name: str, config: dict[str, Any]) -> None:
    """Run one agent's Slack connection until cancelled (network seam).

    Per-agent connection status is owned by the connector supervisor, which catches
    errors here and records them per agent. This runner just opens the connection.
    """
    from fleetent.im_gateway import connector_registry

    app = create_app(agent_name, config)
    # Register the live web client so the cron scheduler can deliver fired-task replies
    # to this agent's Slack at fire time (resolved per fire, cleared on disconnect).
    client = getattr(app, "client", None)
    if client is not None:
        connector_registry.register("slack", agent_name, client)
    try:
        await _run_socket_mode(app, config.get("app_token", ""))
    finally:
        connector_registry.unregister("slack", agent_name)
