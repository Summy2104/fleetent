"""Graceful-shutdown chain: bulkheads + MCP session release ordering.

Each shutdown step is contained (a failing/hanging component is logged and skipped) and
MCP sessions are released only AFTER in-flight runs drain. A teardown error must not
change the process exit path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.runtime import agent_app


async def test_stop_step_contains_errors():
    async def boom():
        raise RuntimeError("step boom")

    # _stop_step must swallow the error (containment), never raise.
    await agent_app._stop_step("boomy", boom())


async def test_runtime_stop_isolates_failing_component():
    """A failing supervisor.stop_all must not prevent scheduler.shutdown."""

    class _BoomSup:
        async def stop_all(self):
            raise RuntimeError("supervisor down")

    sched = type("S", (), {"shutdown": AsyncMock()})()
    rt = agent_app.AgentRuntime(
        agent=None, supervisor=_BoomSup(), telegram_supervisor=None, scheduler=sched
    )
    await rt.stop()  # must not raise despite supervisor failure
    sched.shutdown.assert_awaited()  # scheduler still stopped


async def test_drain_and_close_releases_mcp_after_drain(monkeypatch):
    """_drain_and_close: rt.stop() → drain → mcp.aclose_all(), in that order."""
    from fleetent.integrations import mcp

    order: list[str] = []

    class _RT:
        async def stop(self):
            order.append("stop")

    async def _fake_aclose():
        order.append("mcp_aclose")

    monkeypatch.setattr(mcp, "aclose_all", _fake_aclose)
    # No in-flight runs → drain returns immediately.
    monkeypatch.setattr("fleetent.runtime.loop._active_runs", 0, raising=False)

    await agent_app._drain_and_close(_RT(), drain_timeout=1.0)

    assert order == ["stop", "mcp_aclose"], f"shutdown order wrong: {order}"


async def test_drain_and_close_contains_mcp_error(monkeypatch):
    from fleetent.integrations import mcp

    class _RT:
        async def stop(self):
            pass

    async def _boom_aclose():
        raise RuntimeError("mcp close boom")

    monkeypatch.setattr(mcp, "aclose_all", _boom_aclose)
    monkeypatch.setattr("fleetent.runtime.loop._active_runs", 0, raising=False)

    # A failing MCP release must be contained — _drain_and_close returns normally.
    await agent_app._drain_and_close(_RT(), drain_timeout=1.0)
