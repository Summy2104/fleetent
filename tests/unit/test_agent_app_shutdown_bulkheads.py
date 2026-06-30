"""Graceful-shutdown chain: bulkheads + MCP session release ordering.

Each shutdown step is contained (a failing/hanging component is logged and skipped) and
MCP sessions are released only AFTER in-flight runs drain. A teardown error must not
change the process exit path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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


async def test_drain_and_close_drives_exit_after_drain(monkeypatch):
    """AAA-8204 ④ 脚手架（实现落地前应见红）。

    实测：全天 17 次重启，15 次在 ~200ms 内 ``active_runs=0`` 完成排空并打
    ``agent_drain_completed``——但进程没退出。疑似 MCP stdio 子进程的非 daemon reader
    线程在 drain 后仍存活，拖住解释器，node 的 ``_stop_running`` 撞满 ``drain_timeout``
    → SIGTERM → SIGKILL，每次重启留 ~35s 下线窗口丢入站消息（放大 ①②③）。

    修复（proposal ④ 改动 1）：``_drain_and_close`` 在 MCP 收尾后必须**确定性驱动进程
    退出**（停 loop / server.shutdown / 终止残留 stdio 子进程），且该步同样舱壁化。

    契约接缝：drain + MCP 收尾后调用退出驱动 ``_drive_exit_after_drain``。该函数尚未实现
    → 本测试见红；它具体要收掉哪些资源，由部署机的 py-spy/faulthandler 存活清单确定后收口。
    """
    from fleetent.integrations import mcp

    monkeypatch.setattr(mcp, "aclose_all", AsyncMock())
    monkeypatch.setattr(mcp, "stop_stdio_reaper", AsyncMock())
    # active_runs=0 → 排空立即完成，走 agent_drain_completed 分支。
    monkeypatch.setattr("fleetent.runtime.loop._active_runs", 0, raising=False)

    driver = MagicMock()
    monkeypatch.setattr(agent_app, "_drive_exit_after_drain", driver, raising=False)

    class _RT:
        async def stop(self):
            pass

    await agent_app._drain_and_close(_RT(), drain_timeout=1.0)

    # 见红判据：当前 _drain_and_close 止于 mcp.aclose_all()，从不驱动退出。
    driver.assert_called_once()
