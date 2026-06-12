from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from fleetent import agent_config
from fleetent.agent_config import AgentFile, ConnectorAccess
from fleetent.identity import Principal
from fleetent.im_gateway import access
from fleetent.runtime.approval_resume import resume_pending_approval

logger = structlog.get_logger(__name__)

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."
_APPROVAL_RE = re.compile(r"^(approve|reject)(\s+always)?\s+([a-f0-9-]{6,36})\s*$", re.IGNORECASE)
_REJECTION_MSG = "你还没有权限使用此 bot，请联系管理员审批。"


def _current_date_tz() -> tuple[str, str]:
    """Return (date string, timezone name) for context injection.

    Date-level granularity keeps the injected system frame stable within a day so it
    does not churn the cacheable prefix on every message. TZ comes from the `TZ` env
    (agent sandbox/runtime config), defaulting to UTC.
    """
    import datetime
    import os
    from zoneinfo import ZoneInfo

    tzname = os.environ.get("TZ") or "UTC"
    try:
        tz: datetime.tzinfo = ZoneInfo(tzname)
    except Exception:  # noqa: BLE001 — bad TZ falls back to UTC, never breaks a turn
        tz, tzname = datetime.UTC, "UTC"
    return datetime.datetime.now(tz).strftime("%Y-%m-%d (%A)"), tzname


def _session_frame_text(sc: SessionContext) -> str:
    """Stable session frame for the system message: platform, scene, date+tz."""
    date_str, tzname = _current_date_tz()
    scene = "私信 (DM)" if sc.chat_type == "dm" else f"频道 {sc.channel_name}".rstrip()
    return (
        f"## 会话上下文\n- 平台: {sc.platform}\n- 场景: {scene}\n- 当前日期: {date_str} ({tzname})"
    )


def _sender_prefix_text(sc: SessionContext) -> str:
    """One-line sender attribution prefixed to the user message."""
    name = f" ({sc.sender_name})" if sc.sender_name else ""
    mention = " [已@bot]" if sc.was_mentioned else ""
    return f"[发送人 {sc.platform}:{sc.sender_id}{name}{mention}]"


@dataclass
class SessionContext:
    """Sender/channel metadata for one inbound message, injected into the LLM.

    Populated by IM adapters. ``platform``/``sender_id``/``chat_type`` are
    platform-provided (authoritative); ``sender_name`` is user-settable.
    """

    platform: str
    sender_id: str
    sender_name: str = ""
    chat_type: str = "dm"  # "dm" | "channel"
    channel_name: str = ""
    was_mentioned: bool = False
    thread_root: str = ""


@dataclass
class FileAttachment:
    """One inbound non-image file attachment (im-file-attachment).

    ``data`` carries the downloaded bytes, or ``None`` when the gateway could not
    deliver the file (download failed or over the size cap); ``note`` then explains
    why so the user message can surface it instead of silently dropping the file.
    Images keep their ``(bytes, mime)`` tuple shape and are NOT represented here.
    """

    data: bytes | None
    mime: str
    filename: str
    note: str = ""


@dataclass
class NormalizedMessage:
    platform: str
    session_id: str
    user_id: str
    text: str
    attachments: list[Any]
    reply_func: Callable[[str], Coroutine[Any, Any, None]]
    channel_id: str = field(default="")
    workspace_id: str = field(default="")
    # Pre-resolved agent name (per-agent-slack-connector): set when the receiving
    # connection already identifies the agent (Slack). Empty = resolve via the index.
    agent_name: str = field(default="")
    # Optional progress callback: called with {"type": "tool_call", "name": ...} before
    # each tool executes. Adapters that want to show real-time feedback supply this;
    # omitting it (None) preserves the existing silent behavior.
    progress_func: Callable[[dict[str, Any]], Awaitable[None]] | None = field(default=None)
    # Optional sender/channel metadata injected into the LLM (im-message-context).
    # None = no context injected (behavior identical to before).
    session_context: SessionContext | None = field(default=None)
    # Optional upload callback: called with a list of local image paths generated during
    # this turn. Adapters that support file uploads (e.g. Slack) supply this; omitting it
    # (None) means generated images are not forwarded to the platform.
    upload_func: Callable[[list[str]], Awaitable[None]] | None = field(default=None)
    # Platform IM connectors keyed by platform name (e.g. {"slack": client}). Passed to
    # loop.run() so permission_gate can DM approvers via outbound primitives.
    outbound_connectors: dict[str, Any] = field(default_factory=dict)
    # conversation-address: the persistable delivery target of this run. Built once by the
    # adapter and threaded into run() so a suspend persists it and a resume rebuilds an
    # equivalent context. None for paths that do not supply one (degrades gracefully).
    conversation_address: Any = field(default=None)


async def _noop_progress(_event: dict[str, Any]) -> None:
    """A do-nothing progress callback so a resumed run always has progress wired."""
    return None


def get_agent_for_context(platform: str, channel_id: str, user_id: str) -> AgentFile | None:
    """Resolve agent from the file index: default → None (bare run).

    Bindings-based routing (channel/user) has been removed; the agent is identified by
    the per-agent connector connection. This function now returns only the default agent.
    Zero DB: definitions come from the scanned ``agent.yaml`` index.
    """
    index = agent_config.current()
    name = index.default_agent()
    return None if name is None else index.get(name)


def _get_connector_access(agent: AgentFile | None, platform: str) -> ConnectorAccess:
    """Return the ConnectorAccess for the given platform, or a default-closed policy."""
    if agent is None:
        return ConnectorAccess()
    if platform == "slack" and agent.connectors.slack is not None:
        return agent.connectors.slack.access
    if platform == "telegram" and agent.connectors.telegram is not None:
        return agent.connectors.telegram.access
    return ConnectorAccess()


_IMAGE_MIME_PREFIX = "image/"

_IMAGE_GENERATED_RE = re.compile(r"image generated: (.+)")
_FILE_WRITTEN_RE = re.compile(r"written \d+ bytes to (.+)")


_EGRESS_NOTICE = (
    "（提示：本轮在 workspace 内生成了产物，但无法自动外发。"
    "若需把产物发回，请用 send_file 工具发送。）"
)


def _turn_has_generated_product(messages: list[dict[str, Any]]) -> bool:
    """Whether this turn's tool results signal a generated/written workspace product.

    sandbox-file-egress: the old host ``Path.is_file()`` auto-reflow is structurally
    broken under container execution (``run_code`` / ``write_file`` write inside the
    container; tool results carry container-side paths the host can never locate). We
    no longer infer a host path or auto-upload; we only detect "a product was produced
    this turn" so ``route()`` can emit an explicit egress notice instead of silently
    dropping it. The real delivery path is the agent calling ``send_file``.
    """
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        for pattern in (_IMAGE_GENERATED_RE, _FILE_WRITTEN_RE):
            m = pattern.search(content)
            if m and m.group(1).strip():
                return True
    return False


def _image_attachments(attachments: list[Any]) -> list[tuple[bytes, str]]:
    """Pick out `(bytes, mime)` image attachments; ignore non-image entries."""
    images: list[tuple[bytes, str]] = []
    for att in attachments:
        if (
            isinstance(att, tuple)
            and len(att) == 2
            and isinstance(att[0], (bytes, bytearray))
            and isinstance(att[1], str)
            and att[1].startswith(_IMAGE_MIME_PREFIX)
        ):
            images.append((bytes(att[0]), att[1]))
    return images


def _file_attachments(attachments: list[Any]) -> list[FileAttachment]:
    """Pick out `FileAttachment` items; ignore image tuples and other entries."""
    return [att for att in attachments if isinstance(att, FileAttachment)]


def _safe_filename(name: str) -> str:
    """Sanitise an inbound filename for writing under uploads/.

    Basename-only (drops any path components, defeating `../` traversal), strips
    control characters, and falls back to ``file`` when nothing usable remains.
    The extension is preserved by `os.path.basename` keeping the tail segment.
    """
    base = Path(name).name.replace("\x00", "")
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    # A name that was only separators/dots (e.g. "///", "..") yields nothing useful.
    if not base or base in {".", ".."}:
        return "file"
    return base


def _save_file_to_workspace(
    data: bytes, filename: str, session_id: str, agent_name: str | None
) -> str:
    """Write an inbound file into the session workspace's uploads/ and return a ref.

    The destination is the same per-session sandbox workspace that `read_file` /
    `run_code` are fenced to, so the agent can read the file by the returned
    workspace-relative path in both container and host-degrade modes. ``agent_name``
    mirrors the tools' own fallback (``None`` → ``"default"``) so the key matches the
    workspace the tools resolve. Locating the workspace is a pure directory op — it
    never opens a docker connection.
    """
    import uuid

    from fleetent.tools.builtin_tools import _get_manager

    manager = _get_manager()
    root = manager.workspace_host_path(manager.scope, session_id, agent_name or "default")
    uploads = root / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename)
    dest = uploads / safe
    if dest.exists():
        dest = uploads / f"{uuid.uuid4().hex[:8]}_{safe}"
    dest.write_bytes(data)
    return f"uploads/{dest.name}"


async def _build_user_content(msg: NormalizedMessage, session_id: str) -> str:
    """Build the user message content from text, images, and file attachments (D3/D4).

    Images are saved to uploads and analyzed once (user text as instruction) — base64
    never enters the main context. Non-image files are written into the session
    workspace and referenced by their workspace-relative path so the agent reads them
    on demand via read_file / run_code; files are NOT vision-analyzed, and a file the
    gateway could not deliver surfaces as a placeholder rather than being dropped. With
    neither images nor files this is just the user text (behavior unchanged).
    """
    images = _image_attachments(msg.attachments)
    files = _file_attachments(msg.attachments)
    if not images and not files:
        return msg.text

    sections = [msg.text] if msg.text else []

    if images:
        from fleetent.tools import builtin_tools, vision_client
        from fleetent.tools.registry import ToolContext

        instruction = msg.text or "Describe this image."
        # agent_name=None mirrors the tools' own fallback ("default") since route()
        # does not pass agent_name to run(); the workspace key thus matches the
        # per-session workspace read_file / run_code are fenced to.
        upload_ctx = ToolContext(session_id=session_id, agent_name=None)
        for data, mime in images:
            ref = builtin_tools._save_upload(data, mime, upload_ctx)
            try:
                analysis = await vision_client.analyze(data, instruction)
            except vision_client.VisionError as exc:
                analysis = f"(image analysis failed: {exc})"
            sections.append(f"[图片 {ref}]\n{analysis}")

    for fa in files:
        if fa.data is not None:
            # agent_name is None here to mirror the tools' own fallback ("default"):
            # route() does not pass agent_name to run(), so the workspace key matches.
            ref = _save_file_to_workspace(fa.data, fa.filename, session_id, None)
            sections.append(f"[文件 {fa.filename} 已保存到 {ref}，可用 read_file 或 run_code 读取]")
        else:
            sections.append(f"[文件 {fa.filename} 未能接收：{fa.note or '未知原因'}]")

    return "\n\n".join(sections)


async def _resume_pending_in_session(
    msg: NormalizedMessage, session_id: str, approval_id: str, decision: str
) -> str | None:
    """Execute-or-decline a resolved gated tool and continue the suspended run.

    Builds the tool context + continuation from the message's agent config (mirroring
    the normal turn's run kwargs), then delegates to resume_pending_approval under the
    session lock so the resumed run is serialized against new same-session turns.
    """
    from fleetent import outbound
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.model import ModelPolicySnapshot
    from fleetent.runtime import loop as agent_loop
    from fleetent.runtime.snapshot import _governance_from_file
    from fleetent.session import manager as session_mgr
    from fleetent.tools.registry import ToolContext

    if msg.agent_name:
        agent = agent_config.current().get(msg.agent_name)
    else:
        agent = get_agent_for_context(msg.platform, msg.channel_id, msg.user_id)

    governance = _governance_from_file(agent) if agent else None
    allowed_tools = agent.allowed_tools if agent is not None and agent.allowed_tools else None
    agent_features = agent.features if agent else None
    model_policy = ModelPolicySnapshot.from_agent(agent) if agent else None
    sandbox_mode = await sandbox_enablement.get_effective_mode()

    # conversation-address: rebuild the delivery context from the PERSISTED address (the
    # run's original chat/thread) rather than the message/click that triggered the resume,
    # so resumed output lands where the run started — regardless of entry point. An
    # upgrade-era entry without an address degrades to the triggering context + a warning.
    pending = await session_mgr.get_pending_approval(session_id, approval_id)
    address_dict = pending.get("address") if isinstance(pending, dict) else None
    if isinstance(address_dict, dict):
        addr = outbound.ConversationAddress.from_dict(address_dict)
        reply_func = outbound.make_replier(msg.outbound_connectors, addr)
        upload_func = outbound.make_uploader(msg.outbound_connectors, addr)
        session_context: SessionContext | None = SessionContext(
            platform=addr.platform,
            sender_id=addr.user_id,
            chat_type=addr.chat_type,
            thread_root=addr.thread_root,
        )
        conversation_address: outbound.ConversationAddress | None = addr
    else:
        logger.warning(
            "approval_resume_missing_address", session_id=session_id, approval_id=approval_id
        )
        reply_func = msg.reply_func
        upload_func = msg.upload_func
        session_context = msg.session_context
        conversation_address = None
    progress_func = msg.progress_func or _noop_progress

    tool_context = ToolContext(
        agent_name=agent.name if agent else None,
        features=agent_features or {},
        session_id=session_id,
        session_context=session_context,
        outbound_connectors=msg.outbound_connectors,
    )

    async def continue_run(history: list[dict[str, object]]) -> str:
        return await agent_loop.run(
            messages=history,
            principal=Principal(user_id=msg.user_id, tenant_id="default"),
            reply_func=reply_func,
            allowed_tools=allowed_tools,
            sandbox_mode=sandbox_mode,
            agent_features=agent_features,
            session_id=session_id,
            governance=governance,
            model_policy=model_policy,
            permission_gate_enabled=agent.permission_gate_enabled if agent else True,
            permission_gate_medium_timeout=(
                agent.permission_gate_medium_timeout_seconds if agent else None
            ),
            permission_gate_high_timeout=(
                agent.permission_gate_high_timeout_seconds if agent else None
            ),
            approval_routing=agent.approval if agent else None,
            outbound_connectors=msg.outbound_connectors,
            progress_func=progress_func,
            session_context=session_context,
            conversation_address=conversation_address,
        )

    # upload_func is rebuilt for parity with the inbound path; the resumed run delivers
    # files through the send_file tool (session_context + connectors), so keep a reference
    # bound but unused here — its construction proves the capability is wired, not dropped.
    _ = upload_func

    async with session_mgr.session_lock(session_id):
        history = await session_mgr.load(session_id)
        reply = await resume_pending_approval(
            session_id=session_id,
            approval_id=approval_id,
            decision=decision,  # type: ignore[arg-type]
            messages=history,
            tool_context=tool_context,
            continue_run=continue_run,
        )
        await session_mgr.save(session_id, history)
    return reply


async def route(msg: NormalizedMessage) -> None:
    # Approval commands bypass the agent loop entirely
    m = _APPROVAL_RE.match(msg.text.strip())
    if m:
        from fleetent.governance import approval_store
        from fleetent.governance.permission_gate import _default_gate
        from fleetent.session import manager as session_mgr

        action = m.group(1).lower()
        decision = "approved" if action == "approve" else "rejected"
        # "approve always <id>" grants a persistent allow-always for the call's
        # fingerprint (approval-minimization); only meaningful on approve.
        always = m.group(2) is not None and action == "approve"
        approval_id = m.group(3)
        # The suspended run persisted its pending entry under ITS OWN session. In a
        # plain DM each message is its own session, so the approve command's session
        # differs from the run's — resolve the run's session from the approval row
        # (same as the Slack button path), never assume it equals this message's.
        # Defensive: a store hiccup must not crash the approve command (fall back).
        row = None
        try:
            row = approval_store.get_approval(approval_id)
        except Exception as exc:  # noqa: BLE001 — fall back to this message's session
            logger.warning("approval_row_lookup_failed", approval_id=approval_id, error=str(exc))
        session_id = str(row["session_id"]) if row and row.get("session_id") else msg.session_id

        # Recover authorized decision actors from the persisted pending entry so the
        # gate's authorization check survives a process restart (approval-suspend-resume).
        pending = await session_mgr.get_pending_approval(session_id, approval_id)
        authorized = (
            {str(a) for a in pending["approver_ids"]}
            if pending and pending.get("approver_ids")
            else None
        )
        found = await _default_gate.resolve(
            approval_id=approval_id,
            decision=decision,  # type: ignore[arg-type]
            approver_user_id=msg.user_id,
            always=always,
            authorized_actors=authorized,
        )
        if not found:
            await msg.reply_func(
                f"⚠️ approval {approval_id} not found, unauthorized, or already resolved"
            )
            return
        if pending is None:
            # Resolved, but no suspended run in this session to resume.
            await msg.reply_func(
                f"{'✅' if decision == 'approved' else '❌'} {approval_id} {decision}"
            )
            return
        reply = await _resume_pending_in_session(msg, session_id, approval_id, decision)
        if reply:
            await msg.reply_func(reply)
        return

    # Resolve agent config first — the access gate is per-platform-connector. When the
    # receiving connection already identifies the agent (per-agent-slack-connector stamps
    # msg.agent_name), use it directly; otherwise fall back to default. Zero DB.
    if msg.agent_name:
        agent = agent_config.current().get(msg.agent_name)
    else:
        agent = get_agent_for_context(msg.platform, msg.channel_id, msg.user_id)

    # Local, zero-platform-DB access gate against the connector's access config + an
    # agent-local approval store. No agent resolved (bare run) → default-closed.
    access_cfg = _get_connector_access(agent, msg.platform)
    store = access.LocalApprovalStore(access.APPROVALS_PATH)
    if not access.channel_allowed(access_cfg, msg.channel_id):
        await msg.reply_func(_REJECTION_MSG)
        return
    # Skip user gate when allow_all_users is set OR when the channel is explicitly listed
    # in allow_channels (channel membership implies authorization). Empty allow_channels
    # means "allow all channels" but does NOT grant implicit user access.
    channel_explicitly_allowed = (
        bool(access_cfg.allow_channels) and msg.channel_id in access_cfg.allow_channels
    )
    skip_user_gate = access_cfg.allow_all_users or channel_explicitly_allowed
    if not skip_user_gate and not access.user_allowed(access_cfg, store, msg.user_id):
        # Record the pending user so the platform/admin can approve them later; either
        # way the message never reaches the loop, decided entirely from local state.
        if access_cfg.require_approval:
            store.add_pending(msg.user_id)
        await msg.reply_func(_REJECTION_MSG)
        return

    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.model import ModelPolicySnapshot
    from fleetent.runtime import loop as agent_loop
    from fleetent.runtime import steering
    from fleetent.runtime.cancellation import CancelToken
    from fleetent.runtime.snapshot import _governance_from_file
    from fleetent.session import manager as session_mgr
    from fleetent.skills import available_skills_prompt, collect_disabled_trace

    session_id = msg.session_id

    governance = _governance_from_file(agent) if agent else None
    # Build the user content once (images are analyzed here) — reused by both the
    # steering branch and the normal turn so analysis never runs twice.
    user_content = await _build_user_content(msg, session_id)
    # im-message-context: prefix the sender attribution onto this turn's user message.
    if msg.session_context is not None:
        user_content = f"{_sender_prefix_text(msg.session_context)}\n\n{user_content}"

    # C1 steering: when a run is already in flight for this session, route the new
    # message per the agent's steering_mode BEFORE taking the session lock (taking it
    # would block and silently serialize into a brand-new turn). Default is "steer".
    mode = governance.steering_mode if governance else "steer"
    if steering.is_running(session_id):
        if mode == "interrupt":
            steering.interrupt(session_id)
            await msg.reply_func("⏹️ 已请求停止当前任务。")
            return
        if mode == "steer" and steering.steer(session_id, user_content):
            await msg.reply_func("📝 已把你的补充发给正在进行的任务。")
            return
        if mode == "queue":
            await msg.reply_func("⏳ 正在处理上一条，处理完接着这条。")
        # steer-but-run-just-ended (race) or queue → fall through to the locked path.

    base_system = agent.system_prompt if agent else _SYSTEM
    allowed_tools = agent.allowed_tools if agent is not None and agent.allowed_tools else None
    agent_features = agent.features if agent else None
    model_policy = ModelPolicySnapshot.from_agent(agent) if agent else None
    # SB3: gate run_code on the IM path too; mode is resolved once per process.
    sandbox_mode = await sandbox_enablement.get_effective_mode()
    # System message ordered stable→variable for prefix caching: base system + the
    # <available_skills> catalog. Per-user long-term context is injected by run().
    catalog = available_skills_prompt(allowed_skills=agent.allowed_skills if agent else None)
    disabled_trace = collect_disabled_trace() or None
    system_content = "\n\n".join(p for p in [base_system, catalog] if p)
    # im-message-context: append the stable session frame (platform/scene/date+tz).
    if msg.session_context is not None:
        system_content = f"{system_content}\n\n{_session_frame_text(msg.session_context)}"

    token = CancelToken()
    max_pending = governance.steering_max_pending if governance else 8

    async with session_mgr.session_lock(session_id):
        history = await session_mgr.load(session_id)

        # Consume the restart-recovery flag (agent-side .resume marker): best-effort,
        # never block the turn.
        try:
            if session_mgr.is_resume_pending(session_id):
                logger.info("session_resumed", session_id=session_id)
                session_mgr.clear_resume_pending(session_id)
        except Exception as exc:  # noqa: BLE001 — resume consume must not block the turn
            logger.warning("session_resume_consume_failed", session_id=session_id, error=str(exc))

        # Replace existing system message or insert at position 0
        if history and isinstance(history[0], dict) and history[0].get("role") == "system":
            history[0]["content"] = system_content
        else:
            history.insert(0, {"role": "system", "content": system_content})

        # P3: on_user_input hook (IM path) — deny or rewrite before appending to history.
        if governance is not None and governance.hooks_enabled:
            from fleetent.runtime import hooks
            from fleetent.runtime.hooks import HookContext

            if hooks.has_hooks("on_user_input"):
                _hres = await hooks.dispatch(
                    "on_user_input",
                    HookContext(
                        event="on_user_input",
                        session_id=session_id,
                        agent_name=agent.name if agent else None,
                        user_id=msg.user_id,
                        payload={"content": user_content},
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=governance.hooks_decision_failure == "strict",
                )
                if _hres.decision == "deny":
                    reason = _hres.reason or "请求被策略拒绝"
                    await msg.reply_func(f"⛔ {reason}")
                    return
                if _hres.modified_content is not None:
                    user_content = _hres.modified_content

        history.append({"role": "user", "content": user_content})

        # P4: session_start hook — inject enterprise context after user message appended.
        if governance is not None and governance.hooks_enabled:
            from fleetent.runtime import hooks as _hooks_ss
            from fleetent.runtime.hooks import HookContext as _HCss

            if _hooks_ss.has_hooks("session_start"):
                _ss_res = await _hooks_ss.dispatch(
                    "session_start",
                    _HCss(
                        event="session_start",
                        session_id=session_id,
                        agent_name=agent.name if agent else None,
                        user_id=msg.user_id,
                        payload={"session_id": session_id, "message_count": len(history)},
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=False,
                )
                if _ss_res.inject_context is not None:
                    history.append({"role": "user", "content": _ss_res.inject_context})

        # C1: register the active run so concurrent same-session messages can steer
        # into it (and interrupt it via the cancel token); the registration is removed
        # on exit so a finished session never looks "running".
        history_len_before = len(history)
        async with steering.register_run(session_id, token, max_pending=max_pending):
            response = await agent_loop.run(
                messages=history,
                principal=Principal(user_id=msg.user_id, tenant_id="default"),
                reply_func=msg.reply_func,
                allowed_tools=allowed_tools,
                disabled_skills_trace=disabled_trace,
                sandbox_mode=sandbox_mode,
                agent_features=agent_features,
                session_id=session_id,
                governance=governance,
                model_policy=model_policy,
                cancel_token=token,
                permission_gate_enabled=agent.permission_gate_enabled if agent else True,
                permission_gate_medium_timeout=(
                    agent.permission_gate_medium_timeout_seconds if agent else None
                ),
                permission_gate_high_timeout=(
                    agent.permission_gate_high_timeout_seconds if agent else None
                ),
                approval_routing=agent.approval if agent else None,
                outbound_connectors=msg.outbound_connectors,
                progress_func=msg.progress_func,
                session_context=msg.session_context,
                conversation_address=msg.conversation_address,
            )

        # P4: session_end hook — observe after run completes, before session save.
        if governance is not None and governance.hooks_enabled:
            from fleetent.runtime import hooks as _hooks_se
            from fleetent.runtime.hooks import HookContext as _HCse

            if _hooks_se.has_hooks("session_end"):
                await _hooks_se.dispatch(
                    "session_end",
                    _HCse(
                        event="session_end",
                        session_id=session_id,
                        agent_name=agent.name if agent else None,
                        user_id=msg.user_id,
                        payload={
                            "session_id": session_id,
                            "user_id": msg.user_id,
                            "reply": response,
                        },
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=False,
                )

        # agent_loop.run() already appended the assistant message to history in-place.
        # Do NOT append again here — that caused duplicate messages in every session.
        await session_mgr.save(session_id, history)

    await msg.reply_func(response)

    # sandbox-file-egress: the regex-sniff host auto-upload is retired (it is
    # structurally broken for container-written products — host Path.is_file() can
    # never match a container-side path). To avoid silently dropping a product, when
    # this turn produced one we surface an explicit notice steering to send_file
    # rather than inferring a host path. Only scan the messages this turn added.
    if _turn_has_generated_product(history[history_len_before:]):
        await msg.reply_func(_EGRESS_NOTICE)
