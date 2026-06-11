"""Resume a run suspended on a pending approval (approval-suspend-resume).

When a gated tool call suspends a run, the pending mapping lives in the session
meta. Once the human decides (Slack button / ``approve``/``reject <id>`` text
command, possibly after a restart), this module applies the decision: on approve
it executes the gated tool through the normal dispatch path (so tool_context /
connectors are injected), on reject it skips execution; either way it injects the
outcome as a context message, clears the pending entry, and continues the run.

The continuation is supplied by the caller as ``continue_run`` so this core stays
decoupled from the loop's wide run-parameter surface (the IM edge builds the thunk
with the agent's full config).
"""

from __future__ import annotations

import datetime
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fleetent.governance import approval_store
from fleetent.session import manager as session_mgr
from fleetent.tools.registry import ToolContext, dispatch

logger = logging.getLogger(__name__)

# Generous default: coroutines no longer suspend on a decision, so a pending
# approval may legitimately outlive several restarts before it is reconciled.
_DEFAULT_EXPIRY_SECONDS = 24 * 3600


async def _execute_tool(tool_name: str, tool_args: Any, tool_context: ToolContext) -> str:
    """Run an approved tool through dispatch (authorization already passed at approval)."""
    result = dispatch(tool_name, tool_args, tool_context=tool_context)
    if inspect.iscoroutine(result):
        result = await result
    return str(result)


async def resume_pending_approval(
    *,
    session_id: str,
    approval_id: str,
    decision: Literal["approved", "rejected"],
    messages: list[dict[str, object]],
    tool_context: ToolContext,
    continue_run: Callable[[list[dict[str, object]]], Awaitable[str]],
) -> str | None:
    """Apply an approval decision and continue the suspended run.

    Returns the continuation's final reply, or ``None`` when there is no matching
    pending approval (already resolved/expired — idempotent no-op).
    """
    entry = await session_mgr.get_pending_approval(session_id, approval_id)
    if entry is None:
        return None

    tool_name = str(entry.get("tool_name", ""))
    if decision == "approved":
        result = await _execute_tool(tool_name, entry.get("tool_args"), tool_context)
        note = f"[审批 {approval_id} 已批准，{tool_name} 执行结果：{result}]"
    else:
        note = f"[审批 {approval_id} 已被用户拒绝，{tool_name} 未执行]"

    messages.append({"role": "user", "content": note})
    await session_mgr.remove_pending_approval(session_id, approval_id)
    return await continue_run(messages)


def _parse_iso(value: object) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


async def reconcile_expired_approvals(*, expiry_seconds: int = _DEFAULT_EXPIRY_SECONDS) -> int:
    """Time out pending approvals older than ``expiry_seconds`` and clear their entries.

    Unlike the legacy blanket cleanup, this PRESERVES non-expired pending approvals so
    they survive a process restart and remain resolvable (approval-suspend-resume). For
    each expired approval the row is marked ``timeout`` and the session's
    ``pending_approvals`` entry is removed, leaving the session consistent. Returns the
    number reconciled. Safe to call at startup.
    """
    pending = approval_store.list_approvals(status="pending")
    if not pending:
        return 0
    now = datetime.datetime.now(datetime.UTC)
    count = 0
    for row in pending:
        created = _parse_iso(row.get("created_at"))
        if created is None or (now - created).total_seconds() < expiry_seconds:
            continue
        approval_id = str(row["id"])
        approval_store.update_approval(
            id=approval_id, status="timeout", resolved_at=now.isoformat()
        )
        session_id = row.get("session_id")
        if session_id:
            # remove_pending_approval is non-locking (callers hold the session lock);
            # reconcile runs outside any run, so acquire the lock here.
            async with session_mgr.session_lock(str(session_id)):
                await session_mgr.remove_pending_approval(str(session_id), approval_id)
        count += 1
    if count:
        logger.info("approvals_reconciled_expired count=%d", count)
    return count
