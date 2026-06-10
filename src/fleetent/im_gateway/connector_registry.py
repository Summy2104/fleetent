"""Process-level registry of live IM connectors, keyed by (platform, agent).

The cron scheduler fires outside any inbound-message context, so it cannot reuse the
per-message ``outbound_connectors`` the IM adapters build on the fly. Instead each
adapter registers its live client/bot here when it connects and clears it on
disconnect; the scheduler resolves the current connector for a task's target platform
at fire time. No platform imports — this is agent-runtime infra consumed by im_gateway
and cron_scheduler.
"""

from __future__ import annotations

from typing import Any

# {(platform, agent_name): connector}. Module-level by design (one process = one agent
# in standalone; the platform process keys by agent_name). Tests clear via `_clear`.
_connectors: dict[tuple[str, str], Any] = {}


def register(platform: str, agent_name: str, connector: Any) -> None:
    """Record a live connector for (platform, agent_name)."""
    _connectors[(platform, agent_name)] = connector


def unregister(platform: str, agent_name: str) -> None:
    """Drop a connector on disconnect. Idempotent."""
    _connectors.pop((platform, agent_name), None)


def snapshot(agent_name: str) -> dict[str, Any]:
    """Return ``{platform: connector}`` for all live connectors of this agent."""
    return {platform: conn for (platform, name), conn in _connectors.items() if name == agent_name}


def _clear() -> None:
    """Test hook: drop all registered connectors."""
    _connectors.clear()
