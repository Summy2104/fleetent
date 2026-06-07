"""Interaction tools: clarify (structured user question) and todo (session scratch pad).

clarify:  suspends the agent loop waiting for a user answer via user_input_gate.
          IM gateway layers render choices as buttons (Slack/Telegram) or text.
todo:     in-memory, session-scoped task list for long-task progress tracking.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Literal

from fleetent.tools.registry import ToolContext, tool

logger = logging.getLogger(__name__)

# ── clarify ───────────────────────────────────────────────────────────────────


@tool
async def clarify(
    question: Annotated[str, "向用户提出的问题"],
    choices: Annotated[list[str] | None, "可选的选项列表（None 表示开放问答）"] = None,
    tool_context: ToolContext | None = None,
    timeout: float = 300.0,
) -> str:
    """Suspend the agent loop and wait for a user answer.

    With choices: IM platforms render interactive buttons (Slack Block Kit,
    Telegram InlineKeyboard). Without choices: open-ended text input.
    Returns the user's answer string, or a timeout message after `timeout` seconds.
    """
    from fleetent.governance import user_input_gate as uig

    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else f"clarify-{uuid.uuid4().hex[:8]}"
    )

    return await uig.wait_for_answer(session_id, timeout=timeout)


# ── todo ──────────────────────────────────────────────────────────────────────

# In-memory store: session_id → list of task strings.
# Intentionally not persisted — todo is a scratch pad for the current session.
_todo_store: dict[str, list[str]] = {}


@tool
def todo(
    action: Annotated[Literal["set", "get", "clear"], "操作类型"],
    items: Annotated[list[str] | None, "任务列表（action='set' 时必填）"] = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Manage a session-scoped task list (in-memory scratch pad).

    set: replace the entire list; get: return current list; clear: empty it.
    The list is not persisted — it lives only for the current session.
    """
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "default"
    )

    if action == "set":
        if not items:
            return "error: action='set' 需要提供 items 列表"
        _todo_store[session_id] = list(items)
        return f"任务列表已设置（{len(items)} 项）"

    if action == "get":
        current = _todo_store.get(session_id, [])
        if not current:
            return "任务列表为空"
        lines = [f"{i + 1}. {item}" for i, item in enumerate(current)]
        return "\n".join(lines)

    if action == "clear":
        _todo_store.pop(session_id, None)
        return "任务列表已清空"

    return f"error: 未知操作 {action!r}，可选值为 set / get / clear"
