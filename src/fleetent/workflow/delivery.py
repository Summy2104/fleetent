"""Shared delivery for workflow notify steps and terminal-run notifications.

Mirrors the cron delivery model: an explicit target wins, otherwise fall back to
the run's creation ``origin``. Sends through the in-process IM connectors via
``outbound.send_to``. Kept in one place so the notify step (delivery is its job,
failure fails the step) and the engine's best-effort terminal notification share
one resolver.
"""

from __future__ import annotations

from typing import Any

from fleetent.structured_logging import get_logger

logger = get_logger("workflow_delivery")

# (platform, target, target_type, thread)
Target = tuple[str, str, str, Any]


def resolve_target(to: Any, origin: dict[str, Any] | None) -> Target | None:
    """Resolve a delivery target: explicit ``to`` wins, else the creation ``origin``.

    ``to`` may be a mapping ``{platform, target, target_type?, thread?}``. ``origin`` is a
    cron-style origin mapping. Returns None when neither yields a deliverable address.
    """
    if isinstance(to, dict):
        platform = to.get("platform")
        target = to.get("target")
        if platform and target:
            return (platform, target, to.get("target_type", "user"), to.get("thread"))
    if isinstance(origin, dict):
        from fleetent import outbound

        addr = outbound.ConversationAddress.from_cron_origin(origin)
        if addr.platform and addr.chat_id:
            return (addr.platform, addr.chat_id, addr.target_type, addr.thread_id)
    return None


async def send(target: Target, text: str, connectors: dict[str, Any]) -> str | None:
    """Send ``text`` to ``target`` via the matching connector. Returns an error string or None.

    A missing connector for the resolved platform is an error string (the caller decides
    whether that fails a step or is merely logged for best-effort terminal delivery).
    """
    from fleetent import outbound

    platform, to, target_type, thread = target
    connector = connectors.get(platform)
    if connector is None:
        return f"no connector for platform {platform!r}"
    try:
        receipt = await outbound.send_to(
            platform, connector, to, text, target_type=target_type, thread=thread
        )
    except Exception as exc:  # noqa: BLE001 — delivery failure is reported, never raised
        logger.warn("workflow_delivery_failed", platform=platform, error=exc)
        return str(exc)
    return None if receipt.ok else (receipt.error or "delivery returned false")
