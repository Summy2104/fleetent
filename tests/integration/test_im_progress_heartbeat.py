"""End-to-end heartbeat timing through real run() + _heartbeat_during (im-progress-heartbeat).

Exercises the real run() wrapper + heartbeat task + _progress_heartbeat with real event-loop
timing; only _run_inner is stubbed to a silent sleep (the gap the heartbeat must cover).
"""

from __future__ import annotations

import asyncio

from fleetent.runtime import loop


async def test_heartbeats_fire_during_silent_run_and_stop_after(monkeypatch):
    monkeypatch.setattr(loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    events: list[dict] = []

    async def progress(evt: dict) -> None:
        events.append(evt)

    async def silent_inner(**kwargs) -> str:
        await asyncio.sleep(0.06)  # a silent stretch: no tool_call events at all
        return "final"

    monkeypatch.setattr(loop, "_run_inner", silent_inner)

    out = await loop.run(messages=[], progress_func=progress, is_sub_agent=False)
    assert out == "final"

    heartbeats = [e for e in events if e.get("type") == "heartbeat"]
    assert len(heartbeats) >= 2  # indicator stayed alive through the silent run
    assert all(isinstance(e["elapsed_s"], int) for e in heartbeats)

    # after run() returned, the heartbeat task is cancelled — no further events
    count = len(events)
    await asyncio.sleep(0.05)
    assert len(events) == count


async def test_sub_agent_run_emits_no_heartbeats(monkeypatch):
    monkeypatch.setattr(loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    events: list[dict] = []

    async def progress(evt: dict) -> None:
        events.append(evt)

    async def silent_inner(**kwargs) -> str:
        await asyncio.sleep(0.05)
        return "child"

    monkeypatch.setattr(loop, "_run_inner", silent_inner)

    out = await loop.run(messages=[], progress_func=progress, is_sub_agent=True)
    assert out == "child"
    assert [e for e in events if e.get("type") == "heartbeat"] == []
