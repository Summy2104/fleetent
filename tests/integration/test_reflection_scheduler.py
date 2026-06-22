from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from fleetent.reflection import scheduler


@pytest.fixture(autouse=True)
def _reset_scheduler_task():
    scheduler._reflection_task = None
    yield
    task = scheduler._reflection_task
    if task is not None and not task.done():
        task.cancel()
    scheduler._reflection_task = None


async def test_start_reflection_scheduler_creates_task_and_stop_cancels_it():
    task = scheduler.start_reflection_scheduler(interval=0.01)
    assert task is not None
    assert not task.done()
    await scheduler.stop_reflection_scheduler()
    assert task.done()
    assert scheduler._reflection_task is None


async def test_stop_reflection_scheduler_noop_when_no_task():
    assert scheduler._reflection_task is None
    await scheduler.stop_reflection_scheduler()
    assert scheduler._reflection_task is None


async def test_start_reflection_scheduler_is_idempotent():
    first = scheduler.start_reflection_scheduler(interval=0.01)
    second = scheduler.start_reflection_scheduler(interval=0.01)
    assert first is second
    await scheduler.stop_reflection_scheduler()


async def test_reflection_loop_periodically_calls_run_reflection(monkeypatch):
    calls: list[tuple[str, bool | None]] = []
    policy = scheduler.AutoMaintenancePolicy(allow_low_risk=True)

    async def _run(
        scope: str,
        *,
        auto_policy: scheduler.AutoMaintenancePolicy | None = None,
    ) -> None:
        calls.append((scope, None if auto_policy is None else auto_policy.allow_low_risk))

    monkeypatch.setattr(scheduler, "run_reflection", _run)
    scheduler.start_reflection_scheduler(interval=0.001, scope="agent", auto_policy=policy)
    for _ in range(50):
        if len(calls) >= 2:
            break
        await asyncio.sleep(0.005)
    await scheduler.stop_reflection_scheduler()
    assert len(calls) >= 2
    assert all(scope == "agent" for scope, _allow_low_risk in calls)
    assert all(allow_low_risk is True for _scope, allow_low_risk in calls)


async def test_reflection_loop_continues_after_failure(monkeypatch):
    calls = 0

    async def _boom_then_ok(
        scope: str,
        *,
        auto_policy: scheduler.AutoMaintenancePolicy | None = None,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(f"{scope} boom")

    monkeypatch.setattr(scheduler, "run_reflection", _boom_then_ok)
    mock_logger = MagicMock()
    with patch("fleetent.reflection.scheduler._logger", mock_logger):
        scheduler.start_reflection_scheduler(interval=0.001, scope="agent")
        for _ in range(50):
            if calls >= 2:
                break
            await asyncio.sleep(0.005)
        await scheduler.stop_reflection_scheduler()
    assert calls >= 2
    assert mock_logger.warn.called
