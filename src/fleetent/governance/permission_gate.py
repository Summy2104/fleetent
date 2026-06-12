"""Human-in-the-loop permission gate.

Tools annotated with a risk_level pause execution until an approver resolves
the request (or the timeout elapses). State is persisted to the agent-side
approval store so an audit trail survives restarts.

Approval routing is driven by ApprovalRouting from agent_config: approvers are
contacted via im_gateway outbound DM; actor identifiers stored as opaque strings.
No platform imports.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fleetent.governance import approval_allowlist_store as allowlist
from fleetent.governance import approval_store

logger = logging.getLogger(__name__)

ApprovalResult = Literal["approved", "rejected", "timeout", "pending"]


def _resolves_to_requester(approval_routing: Any | None, risk_level: str, tool_name: str) -> bool:
    """True when the routing for this call includes the ``requester`` sentinel."""
    if approval_routing is None:
        return False
    from fleetent.agent_config import REQUESTER_SENTINEL, resolve_approvers

    addresses, _policy = resolve_approvers(approval_routing, risk_level, tool_name)
    return any(platform == REQUESTER_SENTINEL for platform, _ in addresses)


class PermissionGate:
    def __init__(self, medium_timeout: float = 300.0, high_timeout: float = 3600.0) -> None:
        self._medium_timeout = medium_timeout
        self._high_timeout = high_timeout
        # Registry of approval_ids that are registered + awaiting a decision. No
        # asyncio.Event: the run is suspended (not blocked), so nothing waits in-process
        # (approval-suspend-resume). Resolution finalizes against this set.
        self._pending: set[str] = set()
        # Per-pending-approval fingerprint context (approval-minimization) so resolve()
        # can persist an allow-always grant for the right (scope, tool) on "approve always".
        self._pending_fp: dict[str, tuple[str, str, str]] = {}
        # Per-pending-approval authorized decision actors: only these identities may
        # resolve the request (requester when sentinel-routed + reached approvers).
        self._authorized: dict[str, set[str]] = {}

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

        # approval-minimization: a prior "approve always" grant for this exact
        # (requester, tool, args) fingerprint auto-approves without paging anyone.
        scope_key = requester_user_id
        fp = allowlist.fingerprint(scope_key, tool_name, tool_args)
        if allowlist.is_allowed(fp):
            approval_store.update_approval(
                id=approval_id,
                status="auto_approved",
                resolved_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
            logger.info(
                "approval_auto_approved id=%s tool=%s scope=%s", approval_id, tool_name, scope_key
            )
            return "approved"
        self._pending_fp[approval_id] = (fp, scope_key, tool_name)

        # The requester sentinel routes the prompt back to the conversation; it is
        # always reachable here because the gate only runs with a live reply_func
        # (the loop guards on it).
        requester_routed = _resolves_to_requester(approval_routing, risk_level, tool_name)

        # Resolve and contact approvers via outbound DM (D2, D3).
        approver_user_ids = await self._notify_approvers(
            approval_id=approval_id,
            tool_name=tool_name,
            risk_level=risk_level,
            approval_routing=approval_routing,
            outbound_connectors=outbound_connectors or {},
        )

        # No approvers reachable → default-closed reject immediately (D5).
        if not approver_user_ids and not requester_routed:
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
            self._pending_fp.pop(approval_id, None)
            logger.info(
                "approval_rejected_no_approver id=%s tool=%s risk=%s",
                approval_id,
                tool_name,
                risk_level,
            )
            return "rejected"

        # Authorized decision actors: the requester (when sentinel-routed) plus
        # outbound approvers actually reached — stored both as the qualified
        # "platform:target" tag and the bare target id so IM callers (bare
        # msg.user_id) and qualified actors both pass the resolve() check.
        authorized: set[str] = set()
        for actor in approver_user_ids:
            authorized.add(actor)
            authorized.add(actor.partition(":")[2])
        if requester_routed:
            authorized.add(requester_user_id)
        self._authorized[approval_id] = authorized

        if requester_routed:
            # The in-flight notice doubles as the requester's approval prompt.
            # Interactive blocks ride along when the reply channel supports them
            # (Slack); a TypeError from a text-only channel degrades to plain text.
            from fleetent.outbound import approval_prompt_blocks

            prompt = (
                f"🔐 Tool `{tool_name}` requires your approval (risk: {risk_level}).\n"
                f"Approval ID: `{approval_id}`\n"
                f"Reply with: `approve {approval_id}` or `reject {approval_id}`"
            )
            try:
                await reply_func(
                    prompt, blocks=approval_prompt_blocks(approval_id, tool_name, risk_level)
                )
            except TypeError:
                await reply_func(prompt)
        else:
            # Notify requester that the request is in flight.
            await reply_func(
                f"⏳ Tool `{tool_name}` requires approval (risk: {risk_level}). "
                f"Approval ID: `{approval_id}` — waiting for approver."
            )

        # Non-blocking: the run suspends instead of awaiting a decision here. The
        # approval stays registered until resolve() finalizes it (which may be after
        # a restart). approvals row remains status=pending.
        self._pending.add(approval_id)
        logger.info(
            "approval_registered_pending id=%s tool=%s risk=%s",
            approval_id,
            tool_name,
            risk_level,
        )
        return "pending"

    def authorized_actors(self, approval_id: str) -> set[str]:
        """Identities allowed to decide a pending approval (for the loop to persist)."""
        return set(self._authorized.get(approval_id, set()))

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

        from fleetent.agent_config import REQUESTER_SENTINEL, resolve_approvers
        from fleetent.outbound import approval_prompt_blocks, is_reachable, send_to

        addresses, _policy = resolve_approvers(approval_routing, risk_level, tool_name)
        # The requester sentinel is handled by the caller via reply_func — it is
        # never an outbound address.
        addresses = [(p, t) for p, t in addresses if p != REQUESTER_SENTINEL]
        if not addresses:
            return []

        msg = (
            f"🔐 Approval required for tool `{tool_name}` (risk: {risk_level}).\n"
            f"Approval ID: `{approval_id}`\n"
            f"Reply with: `approve {approval_id}` or `reject {approval_id}`"
        )
        blocks = approval_prompt_blocks(approval_id, tool_name, risk_level)

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
            sent = await send_to(platform, connector, target, msg, blocks=blocks)
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
        always: bool = False,
        authorized_actors: set[str] | None = None,
    ) -> bool:
        """Resolve a pending approval and finalize its record.

        Returns True if the request was pending and the actor is authorized; False if
        unknown/already-resolved or the actor is not authorized. The approver_user_id is
        stored as an opaque actor string (D4). When ``always`` is set and the decision is
        "approved", the pending request's fingerprint is persisted to the allow-list so
        future identical calls auto-approve (approval-minimization).

        Event-free (approval-suspend-resume): no in-process waiter is woken; the caller
        triggers run resumption after a True result. The approvals row is updated to the
        decision here (request_approval no longer finalizes it).

        Restart survival: when the in-memory registry is empty (post-restart), the caller
        supplies ``authorized_actors`` (recovered from the persisted session entry) and
        the pending check falls back to the approvals row status. ``always`` grants are
        skipped after a restart since the fingerprint context is in-memory only.
        """
        in_memory = approval_id in self._pending
        if not in_memory:
            # Post-restart path: trust the persisted approvals row for pending status.
            row = approval_store.get_approval(approval_id)
            if row is None or row.get("status") != "pending":
                return False
        authorized = (
            authorized_actors
            if authorized_actors is not None
            else self._authorized.get(approval_id)
        )
        if authorized is not None and approver_user_id not in authorized:
            logger.warning(
                "approval_unauthorized_actor id=%s actor=%s", approval_id, approver_user_id
            )
            return False
        if always and decision == "approved":
            pending = self._pending_fp.get(approval_id)
            if pending is not None:
                fp, scope_key, tool_name = pending
                allowlist.add_grant(
                    fingerprint=fp,
                    scope_key=scope_key,
                    tool_name=tool_name,
                    created_at=datetime.datetime.now(datetime.UTC).isoformat(),
                    created_by=approver_user_id,
                )
        approval_store.update_approval(
            id=approval_id,
            status=decision,
            resolved_at=datetime.datetime.now(datetime.UTC).isoformat(),
            approver_user_id=approver_user_id,
        )
        self._pending.discard(approval_id)
        self._pending_fp.pop(approval_id, None)
        self._authorized.pop(approval_id, None)
        logger.info("approval_resolved id=%s decision=%s", approval_id, decision)
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
