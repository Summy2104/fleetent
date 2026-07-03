"""Outbound connector resolution for IM delivery (agent-hosted-im, unified path).

Every runtime — standalone and node-managed — self-hosts its IM connection, so a healthy
runtime always has a live process-local connector injected into the message and registered
in :mod:`fleetent.im_gateway.connector_registry`. There is no queue-backed proxy and no node
drain: managed and standalone share the single direct-send path.

``resolve_for_runtime`` is fail-fast (D5): when managed but no connector is resolvable it logs
an error carrying the diagnostic signal rather than silently returning ``{}``, so a delivery
miss is observable. ``notify_user`` (directed-reach) reverse-resolves the user's IM addresses
through the injected agent-side resolver (node loopback under managed; empty under standalone)
and fans out over the live connectors.
"""

from __future__ import annotations

from typing import Any

from fleetent.structured_logging import get_logger

_logger = get_logger("outbound_connectors")

_MANAGED_PLATFORMS = ("slack", "telegram")


def is_node_managed_runtime() -> bool:
    """Whether this agent process is running under node-managed placement.

    Converged onto the single delivered signal (agent-hosted-im): see
    :func:`fleetent.runtime_placement.is_managed`.
    """
    from fleetent import runtime_placement

    return runtime_placement.is_managed()


async def notify_user(
    user_id: str,
    message: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> None:
    """Directed-reach: DM a user across all their bound IM channels (agent-hosted-im).

    Reverse-resolves ``user_id`` to its IM addresses via the injected agent-side address
    resolver (:func:`fleetent.im_gateway.access.resolve_addresses` — node loopback under
    managed, empty under standalone), then fans out over the process-local live connectors.
    Non-managed / no bindings / a single channel failure are all logged, never raised: a
    directed-reach send is best-effort and must never abort the caller.
    """
    if not is_node_managed_runtime():
        _logger.debug("notify_user_non_managed_skip", user_id=user_id)
        return

    from fleetent import agent_config, outbound
    from fleetent.im_gateway import access, connector_registry

    try:
        bindings = access.resolve_addresses(user_id)
    except Exception as exc:  # noqa: BLE001 — directed-reach lookup is best-effort
        _logger.warn("directed_reach_address_lookup_failed", user_id=user_id, exception=exc)
        return
    if not bindings:
        _logger.info("directed_reach_no_bindings", user_id=user_id)
        return

    agent = agent_config.active_agent()
    agent_name = agent.name if agent is not None else "default"
    connectors = connector_registry.snapshot(agent_name)

    for binding in bindings:
        platform = str(binding.get("platform", ""))
        platform_user_id = str(binding.get("platform_user_id", ""))
        connector = connectors.get(platform)
        try:
            await outbound.send_to(
                platform,
                connector,
                platform_user_id,
                message,
                target_type="user",
                blocks=blocks,
            )
        except Exception as exc:  # noqa: BLE001 — one channel failing must not stop fan-out
            _logger.warn(
                "directed_reach_channel_delivery_failed",
                user_id=user_id,
                platform=platform,
                exception=exc,
            )


def resolve_for_runtime(
    agent_name: str | None, connectors: dict[str, Any] | None
) -> dict[str, Any]:
    """Return the effective outbound connectors for this runtime, fail-fast on a managed miss.

    A non-empty ``connectors`` (the live process-local connectors, standalone or managed) is
    returned as-is. Otherwise, under managed placement the absence of a live connector is a
    real fault — logged as an error with the diagnostic signal (D5) — while a standalone
    non-IM turn is a quiet ``{}``. Never fabricates a queue proxy.
    """
    if connectors:
        return connectors
    if is_node_managed_runtime():
        _logger.error(
            "outbound_connectors_missing_under_managed",
            agent=agent_name,
            managed=True,
            platforms=list(_MANAGED_PLATFORMS),
            detail=(
                "node-managed agent has no live IM connector; the agent-hosted supervisor "
                "did not register one (missing/invalid IM token or supervisor start failure)"
            ),
        )
    return {}
