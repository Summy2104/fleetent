"""Mode-aware outbound connector resolution for IM delivery.

Standalone runtimes send through live process-local connectors. Node-managed runtimes
have no live IM connector in the agent process, so they expose queue-backed connector
proxies instead; node drains the agent-side queue and delivers with its own connector.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fleetent.im_gateway import outbound_queue_store

_MANAGED_PLATFORMS = ("slack", "telegram")


class ManagedOutboundConnector:
    """Queue-backed connector proxy used by node-managed agent processes."""

    def __init__(self, *, agent_name: str, platform: str) -> None:
        self.agent_name = agent_name
        self.platform = platform

    def enqueue_text(
        self,
        *,
        target: str,
        text: str,
        target_type: str = "user",
        thread: Any = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return outbound_queue_store.enqueue(
            platform=self.platform,
            address={"target": target, "target_type": target_type, "thread": thread},
            payload={"kind": "text", "text": text, "blocks": blocks or []},
            dedup_key=self._dedup_key("text"),
        )

    def enqueue_file(
        self,
        *,
        target: str,
        path: str,
        target_type: str = "user",
        thread: Any = None,
    ) -> dict[str, Any]:
        return outbound_queue_store.enqueue(
            platform=self.platform,
            address={"target": target, "target_type": target_type, "thread": thread},
            payload={"kind": "file", "path": path},
            dedup_key=self._dedup_key("file"),
        )

    def _dedup_key(self, kind: str) -> str:
        return f"{self.agent_name}:{self.platform}:{kind}:{uuid.uuid4()}"


def is_node_managed_runtime() -> bool:
    """Whether this agent process is running under node-managed placement."""
    required = (
        os.environ.get("FLEETENT_NODE_ID", "").strip(),
        os.environ.get("FLEETENT_NODE_PLATFORM_URL", "").strip(),
        os.environ.get("FLEETENT_NODE_SERVICE_KEY", "").strip(),
    )
    return all(required)


def resolve_for_runtime(agent_name: str | None, connectors: dict[str, Any] | None) -> dict[str, Any]:
    """Return the effective outbound connectors for this runtime mode."""
    if connectors:
        return connectors
    if not agent_name or not is_node_managed_runtime():
        return {}
    return {
        platform: ManagedOutboundConnector(agent_name=agent_name, platform=platform)
        for platform in _MANAGED_PLATFORMS
    }
