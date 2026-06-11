"""SB8 orphan-sandbox cleanup: enumerate and destroy leftover sandbox workspaces.

A platform crash leaves `sandbox-*` workspaces behind because `destroy_workspace`
only runs on the normal release path. Under the deployment premise that a single
platform instance owns its sandbox backend (design Context), at startup this process
has not yet created any `sandbox-*` workspace, so every such workspace is an orphan
from the previous run and is safe to remove. `cleanup_orphans` is a plain
orchestration entry point — callable from the lifespan hook or by an operator on
demand — and does not depend on any scheduler.

Enumeration is capability-gated: a backend that does not declare `orphan_cleanup`
cannot list leftovers, so cleanup is a no-op (returns 0) and logs that it skipped.
"""

from __future__ import annotations

from fleetent.integrations.sandbox.backend import SANDBOX_NAME_PREFIX, BaseSandboxBackend
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.cleanup")


async def cleanup_orphans(backend: BaseSandboxBackend) -> int:
    """Destroy every orphan `sandbox-*` workspace and return the count destroyed.

    When the backend lacks the `orphan_cleanup` capability, returns 0 without
    enumerating (logging the skip). Otherwise enumerates via
    `backend.list_workspaces(SANDBOX_NAME_PREFIX)` (empty when the backend is
    unavailable -> returns 0). Because Docker's `--filter name=` is substring
    matching, each name is re-checked with `startswith` before destroying so a
    workspace whose name merely contains the prefix mid-string is skipped (D3).
    Destruction is best-effort: `destroy_workspace` is idempotent and does not
    raise. The count and the destroyed names are logged for audit (D4).
    """
    if not backend.capabilities.orphan_cleanup:
        _logger.info("sandbox_cleanup_skipped_unsupported", backend=backend.name)
        return 0
    names = await backend.list_workspaces(SANDBOX_NAME_PREFIX)
    destroyed: list[str] = []
    for name in names:
        if not name.startswith(SANDBOX_NAME_PREFIX):
            _logger.warn("sandbox_cleanup_skipped_non_prefix", name=name)
            continue
        await backend.destroy_workspace(name)
        destroyed.append(name)
    _logger.info("sandbox_cleanup_done", count=len(destroyed), destroyed=destroyed)
    return len(destroyed)
