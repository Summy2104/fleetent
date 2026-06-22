from __future__ import annotations

import asyncio
from contextlib import suppress

from fleetent.structured_logging import get_logger

from .reflection import AutoMaintenancePolicy, run_reflection

_logger = get_logger("reflection.scheduler")
_reflection_task: asyncio.Task[None] | None = None


async def _reflection_loop(
    interval: float,
    *,
    scope: str,
    auto_policy: AutoMaintenancePolicy | None = None,
) -> None:
    """Periodically trigger reflection for one agent scope."""
    while True:
        await asyncio.sleep(interval)
        try:
            await run_reflection(scope, auto_policy=auto_policy)
        except Exception as exc:  # noqa: BLE001 - best-effort resident loop
            _logger.warn("reflection_cycle_failed", scope=scope, error=str(exc))


def start_reflection_scheduler(
    *,
    interval: float,
    scope: str | None = None,
    auto_policy: AutoMaintenancePolicy | None = None,
) -> asyncio.Task[None]:
    """Start the process-local reflection loop if it is not already running."""
    global _reflection_task
    if _reflection_task is not None and not _reflection_task.done():
        return _reflection_task
    if scope is None:
        from fleetent import agent_config

        scope = agent_config.active_agent_or_default().name
    _reflection_task = asyncio.create_task(
        _reflection_loop(interval, scope=scope, auto_policy=auto_policy)
    )
    return _reflection_task


async def stop_reflection_scheduler() -> None:
    """Stop the process-local reflection loop, leaving no residual task."""
    global _reflection_task
    if _reflection_task is None:
        return
    _reflection_task.cancel()
    with suppress(asyncio.CancelledError):
        await _reflection_task
    _reflection_task = None
