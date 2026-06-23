"""Core-loop progress heartbeat: helper + owner-task context manager (im-progress-heartbeat)."""

from __future__ import annotations

import asyncio

import pytest

from fleetent.runtime import loop

# --- _progress_heartbeat coroutine (task 1.1/1.2) ---


async def test_progress_heartbeat_emits_heartbeat_events() -> None:
    events: list[dict] = []

    async def progress(evt: dict) -> None:
        events.append(evt)

    task = asyncio.create_task(loop._progress_heartbeat(progress, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(events) >= 2
    assert all(e["type"] == "heartbeat" for e in events)
    assert all(isinstance(e["elapsed_s"], int) and e["elapsed_s"] >= 0 for e in events)
    # only type + elapsed_s, nothing sensitive
    assert all(set(e.keys()) == {"type", "elapsed_s"} for e in events)


async def test_progress_heartbeat_swallows_progress_errors() -> None:
    calls = {"n": 0}

    async def flaky(evt: dict) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    task = asyncio.create_task(loop._progress_heartbeat(flaky, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # first call raised but the loop kept going (more calls happened)
    assert calls["n"] >= 2


# --- _heartbeat_during context manager (task 1.3/1.4) ---


async def test_heartbeat_during_runs_and_stops(monkeypatch) -> None:
    monkeypatch.setattr(loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    events: list[dict] = []

    async def progress(evt: dict) -> None:
        events.append(evt)

    async with loop._heartbeat_during(progress, is_sub_agent=False):
        await asyncio.sleep(0.05)
    during = len(events)
    assert during >= 2  # heartbeats fired inside the block

    # after exit the task is cancelled — no new events
    await asyncio.sleep(0.05)
    assert len(events) == during


async def test_heartbeat_during_skips_for_sub_agent(monkeypatch) -> None:
    monkeypatch.setattr(loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    events: list[dict] = []

    async def progress(evt: dict) -> None:
        events.append(evt)

    async with loop._heartbeat_during(progress, is_sub_agent=True):
        await asyncio.sleep(0.05)
    assert events == []


async def test_heartbeat_during_skips_when_no_progress_func(monkeypatch) -> None:
    monkeypatch.setattr(loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    async with loop._heartbeat_during(None, is_sub_agent=False):
        await asyncio.sleep(0.05)
    # nothing to assert beyond "no crash / no task" — reaching here is success


# --- run() wraps _run_inner with the heartbeat (task 1.5/1.6) ---


async def test_run_wraps_inner_with_heartbeat(monkeypatch) -> None:
    import contextlib as _cl

    captured: dict = {}

    @_cl.asynccontextmanager
    async def fake_during(progress_func, *, is_sub_agent):
        captured["entered"] = True
        captured["is_sub_agent"] = is_sub_agent
        captured["has_progress"] = progress_func is not None
        yield

    async def fake_inner(**kwargs):
        captured["inner_ran"] = True
        return "ok"

    monkeypatch.setattr(loop, "_heartbeat_during", fake_during)
    monkeypatch.setattr(loop, "_run_inner", fake_inner)

    async def progress(evt: dict) -> None:
        pass

    out = await loop.run(messages=[], progress_func=progress, is_sub_agent=False)
    assert out == "ok"
    assert captured == {
        "entered": True,
        "is_sub_agent": False,
        "has_progress": True,
        "inner_ran": True,
    }
