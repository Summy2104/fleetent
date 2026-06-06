"""Tests for the sandbox idle-sweep maintenance loop (sandbox-runtime-lifecycle-wiring).

Mirrors session_mgr's maintenance-loop semantics: a bare asyncio background task,
idempotent start, fault-isolated iterations, clean stop. The process SandboxManager
is mocked (no real Docker), so these stay unit-level.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.integrations.sandbox import maintenance


@pytest.fixture(autouse=True)
async def _no_leaked_sweep_task() -> AsyncIterator[None]:
    """Cancel any task a test leaves running so module state never bleeds across tests."""
    yield
    await maintenance.stop_idle_sweep()


def _manager_with(sweep: AsyncMock) -> MagicMock:
    mgr = MagicMock()
    mgr.sweep_idle = sweep
    return mgr


async def test_public_api_exports_sweep_controls() -> None:
    """start/stop are reachable from the package root, not just the submodule."""
    from fleetent.integrations.sandbox import start_idle_sweep, stop_idle_sweep

    assert callable(start_idle_sweep)
    assert callable(stop_idle_sweep)


async def test_start_idle_sweep_creates_running_task() -> None:
    task = maintenance.start_idle_sweep(interval=10.0)
    assert isinstance(task, asyncio.Task)
    assert not task.done()


async def test_start_idle_sweep_is_idempotent() -> None:
    first = maintenance.start_idle_sweep(interval=10.0)
    second = maintenance.start_idle_sweep(interval=10.0)
    assert first is second


async def test_stop_idle_sweep_cancels_and_clears() -> None:
    task = maintenance.start_idle_sweep(interval=10.0)
    await maintenance.stop_idle_sweep()
    assert task.done()
    assert maintenance._sweep_task is None


async def test_loop_invokes_sweep_idle_on_each_interval() -> None:
    sweep = AsyncMock()
    with patch("fleetent.tools.builtin_tools._get_manager", return_value=_manager_with(sweep)):
        maintenance.start_idle_sweep(interval=0.01)
        await asyncio.sleep(0.05)
    assert sweep.await_count >= 1


async def test_loop_survives_a_sweep_failure() -> None:
    """A single sweep_idle error is logged and the loop keeps running (fault isolation)."""
    sweep = AsyncMock(side_effect=[RuntimeError("boom"), None, None, None, None, None])
    with patch("fleetent.tools.builtin_tools._get_manager", return_value=_manager_with(sweep)):
        maintenance.start_idle_sweep(interval=0.01)
        await asyncio.sleep(0.06)
    assert sweep.await_count >= 2
