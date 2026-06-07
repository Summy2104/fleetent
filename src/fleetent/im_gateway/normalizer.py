from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import structlog

from fleetent import agent_config
from fleetent.agent_config import AgentAccess, AgentFile
from fleetent.im_gateway import access

logger = structlog.get_logger(__name__)

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."
_APPROVAL_RE = re.compile(r"^(approve|reject)\s+([a-f0-9-]{6,36})\s*$", re.IGNORECASE)
_REJECTION_MSG = "你还没有权限使用此 bot，请联系管理员审批。"


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
    # Owning tenant of the IM connector that produced this message (multi-tenant IM
    # gateway). Empty = single-tenant/legacy. Namespaces the allowlist scope and the
    # session id so the same platform/channel under two owners never collides.
    owner_id: str = field(default="")
    # Pre-resolved agent name (per-agent-slack-connector): set when the receiving
    # connection already identifies the agent (Slack). Empty = resolve via the index.
    agent_name: str = field(default="")


def get_agent_for_context(platform: str, channel_id: str, user_id: str) -> AgentFile | None:
    """Resolve agent from the file index: channel → user → default → None (bare run).

    Zero DB: bindings and definitions come from the scanned ``agent.yaml`` index
    (file-driven-agent-config).
    """
    index = agent_config.current()
    name: str | None = None
    if channel_id:
        name = index.agent_for_channel(platform, channel_id)
    if name is None and user_id:
        name = index.agent_for_user(user_id)
    if name is None:
        name = index.default_agent()
    return None if name is None else index.get(name)


_IMAGE_MIME_PREFIX = "image/"


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


async def _build_user_content(msg: NormalizedMessage) -> str:
    """Build the user message content, extracting images first (D3).

    With no image attachments this is just the user text. With images, each is
    saved to uploads, analyzed once (user text as instruction), and the message
    becomes the user text plus the structured analysis and on-disk references —
    base64 never enters the main context, so the loop routes to the text model.
    Look-back is left to the model via analyze_image on the same references.
    """
    from fleetent.tools import builtin_tools, vision_client

    images = _image_attachments(msg.attachments)
    if not images:
        return msg.text

    instruction = msg.text or "Describe this image."
    sections = [msg.text] if msg.text else []
    for data, mime in images:
        ref = builtin_tools._save_upload(data, mime)
        try:
            analysis = await vision_client.analyze(data, instruction)
        except vision_client.VisionError as exc:
            analysis = f"(image analysis failed: {exc})"
        sections.append(f"[图片 {ref}]\n{analysis}")
    return "\n\n".join(sections)


async def route(msg: NormalizedMessage) -> None:
    # Approval commands bypass the agent loop entirely
    m = _APPROVAL_RE.match(msg.text.strip())
    if m:
        from fleetent.governance.permission_gate import _default_gate

        decision = "approved" if m.group(1).lower() == "approve" else "rejected"
        approval_id = m.group(2)
        found = await _default_gate.resolve(
            approval_id=approval_id,
            decision=decision,  # type: ignore[arg-type]
            approver_user_id=msg.user_id,
        )
        if found:
            await msg.reply_func(
                f"{'✅' if decision == 'approved' else '❌'} {approval_id} {decision}"
            )
        else:
            await msg.reply_func(f"⚠️ approval {approval_id} not found or already expired")
        return

    # Resolve agent config first — the access gate is per-agent. When the receiving
    # connection already identifies the agent (per-agent-slack-connector stamps
    # msg.agent_name), use it directly and skip channel→agent lookup; otherwise fall
    # back to channel → user → default. Zero DB: the index is file-sourced.
    if msg.agent_name:
        agent = agent_config.current().get(msg.agent_name)
    else:
        agent = get_agent_for_context(msg.platform, msg.channel_id, msg.user_id)

    # Local, zero-platform-DB access gate against the agent's own access config + an
    # agent-local approval store. No agent resolved (bare run) → default-closed.
    access_cfg = agent.access if agent else AgentAccess()
    store = access.LocalApprovalStore(access.APPROVALS_PATH)
    if not access.channel_allowed(access_cfg, msg.channel_id):
        await msg.reply_func(_REJECTION_MSG)
        return
    if not access.user_allowed(access_cfg, store, msg.user_id):
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

    # Namespace the session by owner so the same platform/channel under two owners
    # never shares conversation state.
    session_id = f"{msg.owner_id}:{msg.session_id}" if msg.owner_id else msg.session_id

    governance = _governance_from_file(agent) if agent else None
    # Build the user content once (images are analyzed here) — reused by both the
    # steering branch and the normal turn so analysis never runs twice.
    user_content = await _build_user_content(msg)

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
    allowed_tools = agent.allowed_tools or None
    agent_features = agent.features if agent else None
    model_policy = ModelPolicySnapshot.from_agent(agent) if agent else None
    # SB3: gate run_code on the IM path too; mode is resolved once per process.
    sandbox_mode = await sandbox_enablement.get_effective_mode()
    # System message ordered stable→variable for prefix caching: base system + the
    # <available_skills> catalog. Per-user long-term context is injected by run().
    catalog = available_skills_prompt(allowed_skills=agent.allowed_skills if agent else None)
    disabled_trace = collect_disabled_trace() or None
    system_content = "\n\n".join(p for p in [base_system, catalog] if p)

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
        async with steering.register_run(session_id, token, max_pending=max_pending):
            response = await agent_loop.run(
                messages=history,
                user_id=msg.user_id,
                reply_func=msg.reply_func,
                allowed_tools=allowed_tools,
                disabled_skills_trace=disabled_trace,
                sandbox_mode=sandbox_mode,
                agent_features=agent_features,
                session_id=session_id,
                governance=governance,
                model_policy=model_policy,
                cancel_token=token,
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
