from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import structlog

from fleetent import agent_store, im_user_store
from fleetent.agent_store import Agent

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


def get_agent_for_context(platform: str, channel_id: str, user_id: str) -> Agent | None:
    """Resolve agent: channel binding → user binding → default agent → None (bare run)."""
    if channel_id:
        agent = agent_store.get_agent_for_channel(platform, channel_id)
        if agent:
            return agent
    agent = agent_store.get_agent_for_user(user_id)
    if agent:
        return agent
    return agent_store.get_default_agent()


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
    from fleetent import tools, vision_client

    images = _image_attachments(msg.attachments)
    if not images:
        return msg.text

    instruction = msg.text or "Describe this image."
    sections = [msg.text] if msg.text else []
    for data, mime in images:
        ref = tools._save_upload(data, mime)
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
        from fleetent.permission_gate import _default_gate

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

    # Channel allowlist gate — checked before any user-level check. When the platform's
    # connector has allowlist_enforced off, this always passes (backward compatible).
    from fleetent import im_channel_allowlist

    if not im_channel_allowlist.is_allowed(msg.platform, msg.channel_id, msg.workspace_id or None):
        await msg.reply_func(_REJECTION_MSG)
        return

    # Allowlist check — IM users must be approved before interacting
    if not im_user_store.check_allowed_by_user_id(msg.user_id):
        await msg.reply_func(_REJECTION_MSG)
        return

    from fleetent import agent_loop, session_mgr
    from fleetent.memory_layer import load_memories
    from fleetent.skill_registry import available_skills_prompt

    async with session_mgr.session_lock(msg.session_id):
        history = await session_mgr.load(msg.session_id)

        # Resolve agent config: channel → user → default → bare run
        agent = get_agent_for_context(msg.platform, msg.channel_id, msg.user_id)
        base_system = agent.system_prompt if agent else _SYSTEM
        allowed_tools = agent.allowed_tools if agent else None

        # Build the system message ordered stable→variable for prefix caching:
        # base system + the <available_skills> catalog (stable) first, per-user
        # memory last. The model loads any skill it needs on demand via read_skill.
        catalog = available_skills_prompt()
        memory_ctx = load_memories(user_id=msg.user_id)
        parts = [base_system, catalog, memory_ctx]
        system_content = "\n\n".join(p for p in parts if p)

        # Replace existing system message or insert at position 0
        if history and isinstance(history[0], dict) and history[0].get("role") == "system":
            history[0]["content"] = system_content
        else:
            history.insert(0, {"role": "system", "content": system_content})

        history.append({"role": "user", "content": await _build_user_content(msg)})

        response = await agent_loop.run(
            messages=history,
            user_id=msg.user_id,
            reply_func=msg.reply_func,
            allowed_tools=allowed_tools,
        )

        # agent_loop.run() already appended the assistant message to history in-place.
        # Do NOT append again here — that caused duplicate messages in every session.
        await session_mgr.save(msg.session_id, history)

    await msg.reply_func(response)
