"""Agent-initiated outbound messaging primitives (top-level base infra).

Allows the agent to proactively send messages to specified users/channels,
independent of any inbound message context. Used by the permission gate to
contact designated approvers via DM.

No platform imports — consumed by both governance (permission_gate) and the
IM edge face without creating a core→face dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeliveryReceipt:
    """Structured result of one outbound delivery attempt (delivery-receipts, D1).

    Replaces the bare bool so a run can assemble a ground-truth delivery ledger and the
    user-facing fact trailer: `ok` (delivered?), the `target`/`target_type`/`kind`
    (text|file), the `thread`, the platform `provider_ref` (Slack ts / file_id) for audit,
    and `error` on failure. `ok` is the bool replacement (`if receipt.ok:` at call sites).
    """

    ok: bool
    platform: str
    target: str
    target_type: str
    kind: str  # "text" | "file"
    thread: Any = None
    provider_ref: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ConversationAddress:
    """Where a conversation lives — the persistable delivery target of a run.

    A first-class, serializable address `{platform, chat_id, target_type, thread_id,
    user_id}` plus the SessionContext routing fields (`chat_type`, `thread_root`)
    needed to rebuild an equivalent delivery context after an approval suspend/resume.
    Constructed once by an inbound adapter, persisted inside the pending-approval
    entry, and converged with the cron `origin` descriptor so one type drives all
    outbound delivery. Consumed by the `make_replier` / `make_uploader` factories.
    """

    platform: str
    chat_id: str
    target_type: str = "user"
    thread_id: str | None = None
    user_id: str = ""
    chat_type: str = "dm"
    thread_root: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "chat_id": self.chat_id,
            "target_type": self.target_type,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "chat_type": self.chat_type,
            "thread_root": self.thread_root,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationAddress:
        return cls(
            platform=str(data.get("platform", "")),
            chat_id=str(data.get("chat_id", "")),
            target_type=str(data.get("target_type", "user")),
            thread_id=data.get("thread_id"),
            user_id=str(data.get("user_id", "")),
            chat_type=str(data.get("chat_type", "dm")),
            thread_root=str(data.get("thread_root", "")),
        )

    @classmethod
    def from_cron_origin(cls, origin: dict[str, Any]) -> ConversationAddress:
        """Build from a cron `scheduled_tasks.origin` descriptor (same type, one parser)."""
        return cls(
            platform=str(origin.get("platform", "")),
            chat_id=str(origin.get("chat_id", "")),
            target_type=str(origin.get("target_type", "user")),
            thread_id=origin.get("thread_id"),
            user_id=str(origin.get("user_id", "")),
        )


async def send_to(
    platform: str,
    connector: Any,
    target: str,
    text: str,
    *,
    target_type: str = "user",
    thread: Any = None,
    blocks: list[dict[str, Any]] | None = None,
) -> DeliveryReceipt:
    """Send text to target on platform, returning a DeliveryReceipt (never raises).

    ``target_type`` selects DM (``user``) vs a channel/group post (``channel``);
    ``thread`` optionally threads the message (Slack ``thread_ts`` / Telegram topic).
    ``blocks`` is an optional platform-specific rich payload (Slack Block Kit);
    platforms without rich rendering ignore it and send the text fallback.
    """
    from fleetent.outbound_connectors import ManagedOutboundConnector

    if isinstance(connector, ManagedOutboundConnector):
        connector.enqueue_text(
            target=target,
            text=text,
            target_type=target_type,
            thread=thread,
            blocks=blocks,
        )
        return DeliveryReceipt(
            ok=True,
            platform=platform,
            target=target,
            target_type=target_type,
            kind="text",
            thread=thread,
        )

    ref: str | None = None
    err: str | None = None
    if platform == "slack":
        if target_type == "channel":
            ref, err = await _slack_send_channel(connector, target, text, thread, blocks)
        else:
            ref, err = await _slack_send_dm(connector, target, text, blocks)
    elif platform == "telegram":
        ref, err = await _telegram_send(connector, target, text, thread)
    else:
        err = f"unsupported platform: {platform}"
        logger.warning("outbound_unsupported_platform", platform=platform)
    return DeliveryReceipt(
        ok=err is None,
        platform=platform,
        target=target,
        target_type=target_type,
        kind="text",
        thread=thread,
        provider_ref=ref,
        error=err,
    )


async def send_file_to(
    platform: str,
    connector: Any,
    target: str,
    path: str,
    *,
    target_type: str = "user",
    thread: Any = None,
) -> DeliveryReceipt:
    """Send a local file as an attachment to target, returning a DeliveryReceipt (never raises).

    ``target_type`` selects DM (``user``) vs a channel post (``channel``); ``thread``
    optionally threads the delivery (Slack ``thread_ts``). This is the single outbound file
    delivery point shared by the ``send_file`` tool and the IM adapters' upload path.
    """
    from fleetent.outbound_connectors import ManagedOutboundConnector

    if isinstance(connector, ManagedOutboundConnector):
        connector.enqueue_file(
            target=target,
            path=path,
            target_type=target_type,
            thread=thread,
        )
        return DeliveryReceipt(
            ok=True,
            platform=platform,
            target=target,
            target_type=target_type,
            kind="file",
            thread=thread,
        )

    ref: str | None = None
    err: str | None = None
    if platform == "slack":
        ref, err = await _slack_send_file(connector, target, path, target_type, thread)
    elif platform == "telegram":
        ref, err = await _telegram_send_file(connector, target, path)
    else:
        err = f"unsupported platform: {platform}"
        logger.warning("outbound_file_unsupported_platform", platform=platform)
    return DeliveryReceipt(
        ok=err is None,
        platform=platform,
        target=target,
        target_type=target_type,
        kind="file",
        thread=thread,
        provider_ref=ref,
        error=err,
    )


def make_replier(connectors: dict[str, Any], address: ConversationAddress) -> Any:
    """Build a thread-aware text reply closure for an address (no platform branch here).

    The returned ``reply_func(text, blocks=None)`` dispatches through ``send_to`` with the
    address's target/target_type/thread, so every inbound and resume entry constructs its
    reply closure the same way — structurally impossible to drop the thread. A missing
    connector for the address platform is a logged no-op (delivery is best-effort).
    """
    connector = connectors.get(address.platform)

    async def reply_func(text: str, blocks: list[dict[str, Any]] | None = None) -> None:
        if connector is None:
            logger.warning("replier_no_connector", platform=address.platform)
            return
        await send_to(
            address.platform,
            connector,
            address.chat_id,
            text,
            target_type=address.target_type,
            thread=address.thread_id,
            blocks=blocks,
        )

    return reply_func


def make_uploader(connectors: dict[str, Any], address: ConversationAddress) -> Any:
    """Build a thread-aware file upload closure for an address (mirrors ``make_replier``).

    The returned ``upload_func(paths)`` delivers each path through ``send_file_to`` to the
    address's chat/thread. A missing connector is a logged no-op.
    """
    connector = connectors.get(address.platform)

    async def upload_func(paths: list[str]) -> None:
        if connector is None:
            logger.warning("uploader_no_connector", platform=address.platform)
            return
        for path in paths:
            await send_file_to(
                address.platform,
                connector,
                address.chat_id,
                path,
                target_type=address.target_type,
                thread=address.thread_id,
            )

    return upload_func


def make_mcp_authz_deliverer(tool_context: Any) -> Any:
    """Build a per-call MCP authorization-link DM deliverer from a tool context (D8).

    The returned coroutine ``deliver(user_id, agent_id, server_id, url) -> bool`` sends the
    authorization link to the *requesting user themselves* as a private DM
    (``target_type="user"``), NEVER to a shared channel — even when the triggering call
    arrived in a channel — so another participant cannot intercept the link's one-shot
    ``state``. The DM address is the requester's own platform id taken from the inbound
    ``session_context`` (sender), falling back to the conversation address's ``user_id``.

    Like :func:`make_mcp_credential_deliverer`, this has a node-managed fallback: a node-managed
    agent has no live IM connector (the node hosts IM), so the link is enqueued through
    directed-reach (``outbound_connectors.notify_user`` -> ``im_outbound_queue`` -> node drain ->
    DM). In a standalone runtime the live connector DMs the requester directly. Always returns a
    deliverer (never None): managed enqueues; standalone with a connector sends; otherwise it
    reports undelivered so the call still degrades cleanly with a "needs authorization" notice.
    """
    connectors: dict[str, Any] = getattr(tool_context, "outbound_connectors", {}) or {}
    session_context = getattr(tool_context, "session_context", None)
    address = getattr(tool_context, "conversation_address", None)

    platform = getattr(session_context, "platform", "") or getattr(address, "platform", "")
    # The DM recipient is the sender — the requester — not the (possibly channel) chat id.
    target = getattr(session_context, "sender_id", "") or getattr(address, "user_id", "")
    connector = connectors.get(platform) if platform else None

    async def deliver(user_id: str, agent_id: str, server_id: str, url: str) -> bool:
        msg = (
            f"🔐 Authorize MCP server `{server_id}` to act on your behalf:\n{url}\n"
            "Open the link to grant access, then retry your request."
        )
        if connector is not None and platform and target:
            receipt = await send_to(platform, connector, target, msg, target_type="user")
            if not receipt.ok:
                logger.warning(
                    "mcp_authz_dm_failed",
                    server_id=server_id,
                    platform=platform,
                    error=receipt.error,
                )
            return receipt.ok
        # node-managed (no live connector): enqueue a directed-reach DM to the requester.
        from fleetent import outbound_connectors

        if outbound_connectors.is_node_managed_runtime():
            outbound_connectors.notify_user(user_id, msg)
            return True
        logger.info("mcp_authz_link_undeliverable server_id=%s user_id=%s", server_id, user_id)
        return False

    return deliver


def make_mcp_credential_deliverer(tool_context: Any) -> Any:
    """Build a per-call deliverer for the per-user api-key *secure-form* link (Form mode).

    Sibling to :func:`make_mcp_authz_deliverer` with two differences: (1) credential-submission
    wording (not OAuth "authorize"), and (2) a node-managed fallback. A node-managed agent has
    no live IM connector (the node hosts IM), so the link is enqueued through directed-reach
    (``outbound_connectors.notify_user`` -> ``im_outbound_queue`` -> node drain -> DM). In a
    standalone runtime the live connector DMs the requester directly. Always returns a
    deliverer (never None): managed enqueues; standalone with a connector sends; otherwise it
    reports undelivered so the call still degrades cleanly.
    """
    connectors: dict[str, Any] = getattr(tool_context, "outbound_connectors", {}) or {}
    session_context = getattr(tool_context, "session_context", None)
    address = getattr(tool_context, "conversation_address", None)
    platform = getattr(session_context, "platform", "") or getattr(address, "platform", "")
    target = getattr(session_context, "sender_id", "") or getattr(address, "user_id", "")
    connector = connectors.get(platform) if platform else None

    async def deliver(user_id: str, agent_id: str, server_id: str, url: str) -> bool:
        msg = (
            f"🔑 MCP server `{server_id}` needs your API key. Open this secure form to submit "
            f"it — your key goes straight to the server, encrypted, and is never shown in "
            f"chat:\n{url}\nThen retry your request."
        )
        if connector is not None and platform and target:
            receipt = await send_to(platform, connector, target, msg, target_type="user")
            if not receipt.ok:
                logger.warning(
                    "mcp_cred_dm_failed",
                    server_id=server_id,
                    platform=platform,
                    error=receipt.error,
                )
            return receipt.ok
        # node-managed (no live connector): enqueue a directed-reach DM to the requester.
        from fleetent import outbound_connectors

        if outbound_connectors.is_node_managed_runtime():
            outbound_connectors.notify_user(user_id, msg)
            return True
        logger.info("mcp_cred_link_undeliverable server_id=%s user_id=%s", server_id, user_id)
        return False

    return deliver


def approval_prompt_blocks(
    approval_id: str, tool_name: str, risk_level: str, summary: str = ""
) -> list[dict[str, Any]]:
    """Slack Block Kit payload for an approval prompt: summary + three decision buttons.

    The gate passes this payload opaquely; only Slack delivery paths render it.
    Button action_ids are the contract consumed by the Slack ``block_actions`` handler.
    ``summary`` (when non-empty) is a human-readable description of WHAT is being approved
    (e.g. the resolved recipient of a send) so the approver can verify before deciding.
    """
    head = f"🔐 工具 `{tool_name}` 请求执行（风险等级: {risk_level}）"
    if summary:
        head += f"\n{summary}"
    head += f"\nApproval ID: `{approval_id}`"
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": head},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "approval_approve",
                    "text": {"type": "plain_text", "text": "✅ 批准"},
                    "style": "primary",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "action_id": "approval_reject",
                    "text": {"type": "plain_text", "text": "❌ 拒绝"},
                    "style": "danger",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "action_id": "approval_approve_always",
                    "text": {"type": "plain_text", "text": "✅ 始终允许"},
                    "value": approval_id,
                },
            ],
        },
    ]


_LABEL_TIMEOUT_SECONDS = 3.0


async def resolve_recipient_label(
    platform: str, connector: Any, target: str, target_type: str
) -> str:
    """Best-effort human-readable label for a send target; raw id on any failure.

    Slack: a user id → ``@<display_name>`` via ``users_info``; a channel id → ``#<name>``
    via ``conversations_info``. Other platforms (or any error/timeout) fall back to the raw
    ``target`` so an approval prompt is never blocked or delayed by name resolution. Never
    raises. No platform-control-plane dependency — resolution goes only through the injected
    IM connector.
    """
    if platform != "slack" or connector is None or not target:
        return target
    try:
        import anyio

        with anyio.fail_after(_LABEL_TIMEOUT_SECONDS):
            if target_type == "channel":
                resp = await connector.conversations_info(channel=target)
                name = ((resp.get("channel") or {}) if hasattr(resp, "get") else {}).get("name")
                return f"#{name}" if name else target
            resp = await connector.users_info(user=target)
            user = (resp.get("user") or {}) if hasattr(resp, "get") else {}
            profile = user.get("profile") or {}
            name = profile.get("display_name") or profile.get("real_name") or user.get("name")
            return f"@{name}" if name else target
    except Exception as exc:  # noqa: BLE001 — name resolution is best-effort, never blocks
        logger.warning("recipient_label_resolve_failed", target=target, error=str(exc))
        return target


def _preview(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


async def summarize_gated_call(
    tool_name: str, tool_args: Any, platform: str, connector: Any
) -> str:
    """Human-readable one-liner of a gated call for the approval prompt (best-effort).

    For ``send_im_message`` it names the resolved recipient (``@name``/``#channel``), the
    target type (私信/频道), a short text preview, and the attachment count — so the approver
    can verify the recipient before deciding. Other tools get a compact, length-capped
    rendering of their args. Never raises.
    """
    args = tool_args if isinstance(tool_args, dict) else {}
    try:
        if tool_name == "send_im_message":
            target = str(args.get("target", "") or "")
            target_type = str(args.get("target_type", "user") or "user")
            label = await resolve_recipient_label(platform, connector, target, target_type)
            kind = "私信" if target_type == "user" else "频道"
            parts = [f"发送对象：{label}（{kind}）"]
            text = str(args.get("text", "") or "")
            if text:
                parts.append(f"预览：{_preview(text)}")
            files = args.get("files") or []
            if files:
                parts.append(f"附件 {len(files)}")
            return "｜".join(parts)
        # Generic: compact, length-capped key=value rendering.
        rendered = ", ".join(f"{k}={_preview(str(v), 40)}" for k, v in args.items())
        return f"参数：{_preview(rendered, 200)}" if rendered else ""
    except Exception as exc:  # noqa: BLE001 — summary is auxiliary, never blocks the prompt
        logger.warning("gated_call_summary_failed", tool=tool_name, error=str(exc))
        return ""


# Delivery-helper contract (delivery-receipts): return (provider_ref, error). Success →
# (ts/file_id-or-"", None); failure → (None, reason). Never raises (outbound must not abort).
_Result = tuple[str | None, str | None]


def _slack_ref(resp: Any, key: str) -> str:
    """Best-effort provider ref (ts/id) from a Slack response; "" when absent/odd-shaped."""
    try:
        v = resp.get(key) if hasattr(resp, "get") else None
        return str(v) if v is not None else ""
    except Exception:  # noqa: BLE001 — ref extraction must never fail a successful send
        return ""


def _slack_file_ref(resp: Any) -> str:
    try:
        files = resp.get("files") if hasattr(resp, "get") else None
        if files:
            return str(files[0].get("id") or "")
        f = resp.get("file") if hasattr(resp, "get") else None
        if f:
            return str(f.get("id") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


async def _slack_send_channel(
    client: Any,
    channel: str,
    text: str,
    thread: Any = None,
    blocks: list[dict[str, Any]] | None = None,
) -> _Result:
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread:
            kwargs["thread_ts"] = thread
        if blocks is not None:
            kwargs["blocks"] = blocks
        resp = await client.chat_postMessage(**kwargs)
        return _slack_ref(resp, "ts"), None
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the caller
        logger.warning("slack_send_channel_failed", channel=channel, error=str(exc))
        return None, str(exc)


async def is_reachable(platform: str, connector: Any, target: str) -> bool:
    """Check if target is reachable on platform before sending.

    Encodes platform constraints:
    - Slack: any workspace user is reachable via DM (open channel).
    - Telegram: only users who have previously /started the bot are reachable
      (bot must be able to get their chat info).
    """
    from fleetent.outbound_connectors import ManagedOutboundConnector

    if isinstance(connector, ManagedOutboundConnector):
        return True
    if platform == "slack":
        return True  # Slack workspace users are always reachable via conversations.open
    if platform == "telegram":
        return await _telegram_is_reachable(connector, target)
    return False


async def _slack_send_dm(
    client: Any, user_id: str, text: str, blocks: list[dict[str, Any]] | None = None
) -> _Result:
    try:
        result = await client.conversations_open(users=[user_id])
        channel = result["channel"]["id"]
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        resp = await client.chat_postMessage(**kwargs)
        return _slack_ref(resp, "ts"), None
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the gate
        logger.warning("slack_send_dm_failed", user_id=user_id, error=str(exc))
        return None, str(exc)


async def _telegram_send(bot: Any, chat_id: str, text: str, thread: Any = None) -> _Result:
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if thread:
            kwargs["message_thread_id"] = thread
        await bot.send_message(**kwargs)
        return "", None  # telegram client returns no stable ref we record; "" = success-no-ref
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the gate
        logger.warning("telegram_send_message_failed", chat_id=chat_id, error=str(exc))
        return None, str(exc)


async def _slack_send_file(
    client: Any, target: str, path: str, target_type: str, thread: Any
) -> _Result:
    """Upload a local file to Slack via ``files_upload_v2``.

    For a channel post the ``target`` is the channel id used directly; for a DM the
    ``target`` is a user id, resolved to its DM channel via ``conversations_open``
    (same range as ``_slack_send_dm``). A single delivery failure is logged and
    swallowed so the caller's run continues.
    """
    try:
        if target_type == "channel":
            channel = target
        else:
            result = await client.conversations_open(users=[target])
            channel = result["channel"]["id"]
        resp = await client.files_upload_v2(channel=channel, thread_ts=thread, file=path)
        return _slack_file_ref(resp), None
    except Exception as exc:  # noqa: BLE001 — outbound file failure must not abort the caller
        logger.warning("slack_send_file_failed", target=target, path=path, error=str(exc))
        return None, str(exc)


async def _telegram_send_file(bot: Any, chat_id: str, path: str) -> _Result:
    """Send a local file to a Telegram chat via ``bot.send_document``."""
    try:
        await bot.send_document(chat_id=chat_id, document=path)
        return "", None
    except Exception as exc:  # noqa: BLE001 — outbound file failure must not abort the caller
        logger.warning("telegram_send_file_failed", chat_id=chat_id, path=path, error=str(exc))
        return None, str(exc)


async def _telegram_is_reachable(bot: Any, chat_id: str) -> bool:
    """Reachable only if the user has previously /started the bot (chat exists)."""
    try:
        await bot.get_chat(chat_id=chat_id)
        return True
    except Exception:  # noqa: BLE001 — not reachable if any error
        return False
