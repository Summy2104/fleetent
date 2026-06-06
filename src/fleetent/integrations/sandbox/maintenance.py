"""Periodic agent-scope idle reclamation for the sandbox (runtime wiring).

`SandboxManager.sweep_idle` reclaims agent-scope containers idle past `idle_hours`,
but nothing invoked it after the platform/runtime split. This module schedules it
as a bare asyncio background task — mirroring `session_mgr.start_session_maintenance`
(deliberately NOT routed through cron_scheduler/APScheduler): a module-level,
test-resettable task handle, idempotent start, fault-isolated iterations, clean stop.

The process-wide `SandboxManager` is fetched lazily inside the loop
(`builtin_tools._get_manager`) so this module does not import `builtin_tools` at top
level (that would close an import cycle) and does not force the manager to be built
at startup — an empty registry sweeps to a no-op.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from fleetent.observability.structured_logging import get_logger

_logger = get_logger("sandbox.maintenance")

# 30 minutes: agent-scope containers idle past `idle_hours` are reclaimed within
# `idle_hours + this interval`. Module-level so tests inject a tiny value.
_DEFAULT_SWEEP_INTERVAL_SECONDS = 1800.0

# Handle for the process-internal periodic idle-sweep task (agent runtime only).
# Module-level + resettable in tests, mirroring session_mgr._maintenance_task.
_sweep_task: asyncio.Task[None] | None = None


async def _idle_sweep_loop(interval: float) -> None:
    """Periodically reclaim idle agent-scope sandboxes (bare asyncio, no cron_scheduler).

    Each iteration is fault-isolated: a single `sweep_idle` failure is logged and the
    loop continues — one failure MUST NOT kill the resident task and silently stop all
    subsequent reclamation. The manager is fetched lazily so the loop always acts on the
    same process singleton `run_code` uses, and an empty registry is a harmless no-op.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            from fleetent.tools.builtin_tools import _get_manager

            await _get_manager().sweep_idle()
        except Exception as exc:  # noqa: BLE001 — a single failure must not kill the loop
            _logger.warn("sandbox_idle_sweep_iteration_failed", error=str(exc))


def start_idle_sweep(*, interval: float | None = None) -> asyncio.Task[None]:
    """Start the background agent-scope idle-sweep task (agent runtime only).

    Idempotent: a running task is returned as-is rather than replaced. `interval`
    defaults to `_DEFAULT_SWEEP_INTERVAL_SECONDS`; tests inject a tiny value.
    """
    global _sweep_task
    if _sweep_task is not None and not _sweep_task.done():
        return _sweep_task
    if interval is None:
        interval = _DEFAULT_SWEEP_INTERVAL_SECONDS
    _sweep_task = asyncio.create_task(_idle_sweep_loop(interval))
    return _sweep_task


async def stop_idle_sweep() -> None:
    """Cancel the background idle-sweep task, leaving no residual task."""
    global _sweep_task
    if _sweep_task is None:
        return
    _sweep_task.cancel()
    with suppress(asyncio.CancelledError):
        await _sweep_task
    _sweep_task = None
