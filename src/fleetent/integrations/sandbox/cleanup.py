"""SB8 orphan-sandbox cleanup: enumerate and destroy leftover sandbox containers.

A platform crash leaves `sandbox-*` containers behind because `destroy_workspace`
only runs on the normal release path. Under the deployment premise that a single
platform instance owns its Docker daemon (design Context), at startup this process
has not yet created any `sandbox-*` container, so every such container is an orphan
from the previous run and is safe to remove. `cleanup_orphans` is a plain
orchestration entry point — callable from the lifespan hook or by an operator on
demand — and does not depend on any scheduler.
"""

from __future__ import annotations

import logging

from fleetent.integrations.sandbox.client import SANDBOX_NAME_PREFIX, SandboxClient

logger = logging.getLogger(__name__)


async def cleanup_orphans(client: SandboxClient) -> int:
    """Destroy every orphan `sandbox-*` container and return the count destroyed.

    Enumerates via `client.list_containers(SANDBOX_NAME_PREFIX)` (empty when Docker
    is unavailable -> returns 0). Because `docker --filter name=` is substring
    matching, each name is re-checked with `startswith` before destroying so a
    container whose name merely contains the prefix mid-string is skipped (D3).
    Destruction is best-effort: `destroy_workspace` is idempotent and does not
    raise. The count and the destroyed names are logged for audit (D4); writing
    these into a trace is coordinated with SB9.
    """
    names = await client.list_containers(SANDBOX_NAME_PREFIX)
    destroyed: list[str] = []
    for name in names:
        if not name.startswith(SANDBOX_NAME_PREFIX):
            logger.warning("sandbox_cleanup_skipped_non_prefix name=%s", name)
            continue
        await client.destroy_workspace(name)
        destroyed.append(name)
    logger.info("sandbox_cleanup_done count=%d destroyed=%s", len(destroyed), destroyed)
    return len(destroyed)
