"""Interaction tools: clarify (structured user question) and todo (session scratch pad).

clarify:  suspends the agent loop waiting for a user answer via user_input_gate.
          IM gateway layers render choices as buttons (Slack/Telegram) or text.
todo:     session-scoped task list with status tracking, persisted to the
          agent-side {session_id}.todo sibling file (no platform/DB); ephemeral
          in-memory when there is no session.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Literal, assert_never

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

# Ephemeral fallback used ONLY when there is no session_id (e.g. a one-shot CLI
# call): a process-local list that is not persisted. The persistent, session-scoped
# path stores the authoritative list in the agent-side `{session_id}.todo` sibling
# file via session_mgr (no platform, no DB) — see session.manager.read_todo/
# write_todo/clear_todo. Resettable in tests for isolation.
_EPHEMERAL_KEY = "default"
_ephemeral_todo: dict[str, list[dict[str, str]]] = {}


def _render_todo(items: list[dict[str, str]]) -> str:
    if not items:
        return "任务列表为空"
    lines: list[str] = []
    for i, item in enumerate(items):
        status = item.get("status", "pending")
        text = item.get("text", "")
        lines.append(f"{i + 1}. [{status}] {text} (id={item.get('id', '')})")
    return "\n".join(lines)


@tool
def todo(
    action: Annotated[Literal["set", "update", "get", "clear"], "操作类型"],
    items: Annotated[list[str] | None, "任务文本列表（action='set' 时必填）"] = None,
    item_id: Annotated[str | None, "目标任务 id（action='update' 时必填）"] = None,
    status: Annotated[
        Literal["pending", "in_progress", "completed"] | None,
        "目标状态（action='update' 时必填）",
    ] = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Manage a session-scoped, persistent task list with status tracking.

    Items are `{id, text, status}` with status pending / in_progress / completed,
    at most one in_progress. `set` replaces the list (each text → pending); `update`
    changes one item's status by id; `get` returns the list; `clear` empties it.
    With a session_id the list persists to the agent-side `{session_id}.todo` file
    (survives restarts, no platform/DB); without one it degrades to a non-persisted
    in-process list.
    """
    from fleetent.session import manager as session_mgr

    session_id = tool_context.session_id if tool_context is not None else None

    def _load() -> list[dict[str, str]]:
        if session_id:
            return session_mgr.read_todo(session_id)
        return list(_ephemeral_todo.get(_EPHEMERAL_KEY, []))

    def _store(current: list[dict[str, str]]) -> None:
        if session_id:
            session_mgr.write_todo(session_id, current)
        else:
            _ephemeral_todo[_EPHEMERAL_KEY] = current

    if action == "set":
        if not items:
            return "error: action='set' 需要提供 items 列表"
        current = [
            {"id": str(i + 1), "text": text, "status": "pending"} for i, text in enumerate(items)
        ]
        _store(current)
        return f"任务列表已设置（{len(current)} 项）"

    if action == "update":
        if not item_id or status is None:
            return "error: action='update' 需要提供 item_id 与 status"
        current = _load()
        target = next((it for it in current if it.get("id") == item_id), None)
        if target is None:
            return f"error: 未找到 id={item_id} 的任务"
        if status == "in_progress" and any(
            it.get("status") == "in_progress" and it.get("id") != item_id for it in current
        ):
            return "error: 已有任务处于 in_progress，请先将其标记为 completed 再开始新任务"
        target["status"] = status
        _store(current)
        return f"任务 {item_id} 状态已更新为 {status}"

    if action == "get":
        return _render_todo(_load())

    if action == "clear":
        if session_id:
            session_mgr.clear_todo(session_id)
        else:
            _ephemeral_todo.pop(_EPHEMERAL_KEY, None)
        return "任务列表已清空"

    assert_never(action)
