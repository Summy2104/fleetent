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
    # Don't actually kill subprocesses / arm the os._exit(0) watchdog in tests.
    monkeypatch.setattr(agent_app, "_drive_exit_after_drain", lambda *a, **k: None)

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
    monkeypatch.setattr(agent_app, "_drive_exit_after_drain", lambda *a, **k: None)

    # A failing MCP release must be contained — _drain_and_close returns normally.
    await agent_app._drain_and_close(_RT(), drain_timeout=1.0)


async def test_drain_and_close_drives_exit_after_drain(monkeypatch):
    """AAA-8204 ④：drain（``active_runs=0`` → ``agent_drain_completed``）+ MCP 收尾后，
    ``_drain_and_close`` 必须确定性调用退出驱动 ``_drive_exit_after_drain``。

    实测：17 次重启，15 次在 ~200ms 内排空完成却不退出（MCP stdio 子进程的非 daemon
    waitpid 线程拖住解释器），全部走到 ``agent_force_kill``，每次留 ~35s 丢消息窗口。
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

    driver.assert_called_once()


def test_drive_exit_terminates_descendant_tree_then_arms_watchdog(monkeypatch):
    """_drive_exit_after_drain force-kills the descendant tree (SIGTERM→SIGKILL) then arms
    the os._exit watchdog — covering both the lingering-thread and stuck-teardown causes."""
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(agent_app, "_list_descendant_pids", lambda pid: [111, 222])
    monkeypatch.setattr(agent_app, "_pid_alive", lambda pid: True)  # survive SIGTERM → SIGKILL
    monkeypatch.setattr(agent_app.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    armed: list[float] = []
    monkeypatch.setattr(agent_app, "_arm_hard_exit_watchdog", lambda d: armed.append(d))

    agent_app._drive_exit_after_drain(grace=0.0, hard_deadline=4.0)

    import signal as _sig

    assert (111, _sig.SIGTERM) in killed and (222, _sig.SIGTERM) in killed
    assert (111, _sig.SIGKILL) in killed and (222, _sig.SIGKILL) in killed
    assert armed == [4.0]  # watchdog armed after the kill sweep


def test_drive_exit_arms_watchdog_even_when_terminate_raises(monkeypatch):
    """Bulkhead: a failure terminating subprocesses is contained — the os._exit watchdog is
    still armed (a sub-step error must not change the exit path / exit code)."""

    def _boom(grace):
        raise RuntimeError("kill boom")

    monkeypatch.setattr(agent_app, "_terminate_descendant_processes", _boom)
    armed: list[float] = []
    monkeypatch.setattr(agent_app, "_arm_hard_exit_watchdog", lambda d: armed.append(d))

    agent_app._drive_exit_after_drain(grace=0.0, hard_deadline=3.0)

    assert armed == [3.0]


def test_terminate_descendants_is_bulkheaded_per_pid(monkeypatch):
    """One unkillable PID (os.kill raises) must not stop the others from being signalled."""
    monkeypatch.setattr(agent_app, "_list_descendant_pids", lambda pid: [111, 222])
    monkeypatch.setattr(agent_app, "_pid_alive", lambda pid: False)  # gone after SIGTERM
    seen: list[int] = []

    def _kill(pid, sig):
        seen.append(pid)
        if pid == 111:
            raise PermissionError("not allowed")

    monkeypatch.setattr(agent_app.os, "kill", _kill)

    agent_app._terminate_descendant_processes(grace=0.0)  # must not raise

    assert 222 in seen  # the second PID was still signalled despite 111 raising


def test_hard_exit_watchdog_arms_daemon_os_exit(monkeypatch):
    """The watchdog is a started daemon timer whose callback is os._exit(0)."""
    created: dict = {}

    class _FakeTimer:
        def __init__(self, interval, fn):
            created["interval"] = interval
            created["fn"] = fn
            self.daemon = False

        def start(self):
            created["started"] = True

    monkeypatch.setattr(agent_app.threading, "Timer", _FakeTimer)
    exits: list[int] = []
    monkeypatch.setattr(agent_app.os, "_exit", lambda code: exits.append(code))

    agent_app._arm_hard_exit_watchdog(7.0)

    assert created["interval"] == 7.0
    assert created["started"] is True
    created["fn"]()  # firing the timer hard-exits 0
    assert exits == [0]
