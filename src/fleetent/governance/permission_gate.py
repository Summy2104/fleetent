"""Human-in-the-loop permission gate.

Tools annotated with a risk_level pause execution until an approver resolves
the request (or the timeout elapses). State is persisted to the agent-side
approval store so an audit trail survives restarts.

Approval routing is driven by ApprovalRouting from agent_config: approvers are
contacted via im_gateway outbound DM; actor identifiers stored as opaque strings.
No platform imports.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fleetent.governance import approval_store

logger = logging.getLogger(__name__)

ApprovalResult = Literal["approved", "rejected", "timeout"]


class PermissionGate:
    def __init__(self, medium_timeout: float = 300.0, high_timeout: float = 3600.0) -> None:
        self._medium_timeout = medium_timeout
        self._high_timeout = high_timeout
        self._events: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, str] = {}

    async def request_approval(
        self,
        approval_id: str,
        risk_level: str,
        tool_name: str,
        tool_args: dict[str, Any],
        requester_user_id: str,
        reply_func: Callable[..., Coroutine[Any, Any, None]],
        session_id: str = "",
        approval_routing: Any | None = None,
        outbound_connectors: dict[str, Any] | None = None,
        medium_timeout: float | None = None,
        high_timeout: float | None = None,
    ) -> ApprovalResult:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        approval_store.insert_approval(
            id=approval_id,
            session_id=session_id,
            requester_user_id=requester_user_id,
            risk_level=risk_level,
            tool_name=tool_name,
            tool_args=json.dumps(tool_args),
            created_at=now,
        )

        event = asyncio.Event()
        self._events[approval_id] = event

        if risk_level == "medium":
            timeout = medium_timeout if medium_timeout is not None else self._medium_timeout
        else:
            timeout = high_timeout if high_timeout is not None else self._high_timeout

        # Resolve and contact approvers via outbound DM (D2, D3).
        approver_actors = await self._notify_approvers(
            approval_id=approval_id,
            tool_name=tool_name,
            risk_level=risk_level,
            approval_routing=approval_routing,
            outbound_connectors=outbound_connectors or {},
        )

        # No approvers reachable → default-closed reject immediately (D5).
        if not approver_actors:
            await reply_func(
                f"❌ Tool `{tool_name}` requires approval but no approver could be reached "
                f"(risk: {risk_level}). Request rejected."
            )
            resolved_at = datetime.datetime.now(datetime.UTC).isoformat()
            approval_store.update_approval(
                id=approval_id,
                status="rejected",
                resolved_at=resolved_at,
            )
            self._events.pop(approval_id, None)
            logger.info(
                "approval_rejected_no_approver id=%s tool=%s risk=%s",
                approval_id,
                tool_name,
                risk_level,
            )
            return "rejected"

        # Notify requester that the request is in flight.
        await reply_func(
            f"⏳ Tool `{tool_name}` requires approval (risk: {risk_level}). "
            f"Approval ID: `{approval_id}` — waiting for approver."
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            decision = self._decisions.get(approval_id, "rejected")
        except TimeoutError:
            decision = "timeout"

        resolved_at = datetime.datetime.now(datetime.UTC).isoformat()
        approval_store.update_approval(
            id=approval_id,
            status=decision,
            resolved_at=resolved_at,
            approver_actor=self._decisions.get(approval_id + ":actor"),
        )

        self._events.pop(approval_id, None)
        self._decisions.pop(approval_id, None)
        self._decisions.pop(approval_id + ":actor", None)
        logger.info(
            "approval_resolved id=%s tool=%s risk=%s decision=%s",
            approval_id,
            tool_name,
            risk_level,
            decision,
        )
        return decision  # type: ignore[return-value]

    async def _notify_approvers(
        self,
        approval_id: str,
        tool_name: str,
        risk_level: str,
        approval_routing: Any | None,
        outbound_connectors: dict[str, Any],
    ) -> list[str]:
        """Contact approvers via outbound DM. Returns opaque actor tags for those reached."""
        if approval_routing is None:
            return []

        from fleetent.agent_config import resolve_approvers
        from fleetent.outbound import is_reachable, send_to

        addresses, _policy = resolve_approvers(approval_routing, risk_level, tool_name)
        if not addresses:
            return []

        msg = (
            f"🔐 Approval required for tool `{tool_name}` (risk: {risk_level}).\n"
            f"Approval ID: `{approval_id}`\n"
            f"Reply with: `approve {approval_id}` or `reject {approval_id}`"
        )

        reached: list[str] = []
        for platform, target in addresses:
            connector = outbound_connectors.get(platform)
            if connector is None:
                logger.warning(
                    "approval_no_connector platform=%s approval_id=%s", platform, approval_id
                )
                continue
            reachable = await is_reachable(platform, connector, target)
            if not reachable:
                logger.warning(
                    "approval_target_unreachable platform=%s target=%s approval_id=%s",
                    platform,
                    target,
                    approval_id,
                )
                continue
            sent = await send_to(platform, connector, target, msg)
            if sent:
                actor = f"{platform}:{target}"
                reached.append(actor)
            else:
                logger.warning(
                    "approval_send_failed platform=%s target=%s approval_id=%s",
                    platform,
                    target,
                    approval_id,
                )

        return reached

    async def resolve(
        self,
        approval_id: str,
        decision: Literal["approved", "rejected"],
        approver_user_id: str,
    ) -> bool:
        """Resolve an approval request.

        Returns True if the request was found, False if expired or unknown.
        The approver_user_id is stored as an opaque actor string (D4).
        """
        event = self._events.get(approval_id)
        if event is None:
            return False
        self._decisions[approval_id] = decision
        self._decisions[approval_id + ":actor"] = approver_user_id
        event.set()
        return True


_default_gate: PermissionGate = PermissionGate()


def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    """Return approvals from the agent-side store, optionally filtered by status."""
    return approval_store.list_approvals(status=status)


def cleanup_stale_approvals() -> None:
    """Mark all pending approvals as timeout. Call at server startup after a restart."""
    count = approval_store.cleanup_stale()
    if count:
        logger.info("startup_cleanup stale_approvals_marked_timeout count=%d", count)
