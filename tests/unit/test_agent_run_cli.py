"""`fleetent agent run / restart` CLI, PID file, drain, and _stop_running."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.__main__ as cli
import fleetent.agent_config as agent_config
from fleetent.runtime import agent_app


def test_parse_agent_run_defaults():
    ns = cli._parse_agent_run(["support"])
    assert ns.agent_id == "support"
    assert ns.port is None
    assert ns.home is None


def test_parse_agent_run_with_port_and_home(tmp_path):
    ns = cli._parse_agent_run(["support", "--port", "8770", "--home", str(tmp_path)])
    assert ns.agent_id == "support"
    assert ns.port == 8770
    assert ns.home == str(tmp_path)


def test_main_dispatches_agent_run(monkeypatch):
    served = {}

    async def fake_serve(agent_id, *, port=None, home=None):
        served["agent_id"] = agent_id
        served["port"] = port

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support", "--port", "8770"])
    cli.main()
    assert served == {"agent_id": "support", "port": 8770}


def test_main_oneshot_still_works(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run", lambda text, **k: f"echo:{text}")
    monkeypatch.setattr("sys.argv", ["fleetent", "hello", "world"])
    cli.main()
    assert "echo:hello world" in capsys.readouterr().out


async def test_serve_with_port_mounts_http(monkeypatch):
    rt = MagicMock()
    rt.app = MagicMock()
    rt.stop = AsyncMock()
    monkeypatch.setattr(agent_app, "boot", AsyncMock(return_value=rt))
    waited = {"forever": False}
    monkeypatch.setattr(
        agent_app,
        "_wait_forever",
        AsyncMock(side_effect=lambda: waited.__setitem__("forever", True)),
    )

    fake_server = MagicMock()
    fake_server.serve = AsyncMock()
    with patch("uvicorn.Server", return_value=fake_server) as server_cls, patch("uvicorn.Config"):
        await agent_app.serve("support", port=8770)

    server_cls.assert_called_once()  # HTTP listener constructed
    fake_server.serve.assert_awaited_once()
    assert waited["forever"] is False  # did not take the IM-only block path
    rt.stop.assert_awaited_once()


async def test_serve_without_port_opens_no_http(monkeypatch):
    rt = MagicMock()
    rt.app = None
    rt.stop = AsyncMock()
    monkeypatch.setattr(agent_app, "boot", AsyncMock(return_value=rt))
    monkeypatch.setattr(agent_app, "_wait_forever", AsyncMock())

    with patch("uvicorn.Server") as server_cls:
        await agent_app.serve("support")

    server_cls.assert_not_called()  # no HTTP listener without --port
    agent_app._wait_forever.assert_awaited_once()
    rt.stop.assert_awaited_once()


# ── PID file lifecycle ────────────────────────────────────────────────────────


async def test_serve_writes_pid_file_during_run(tmp_path, monkeypatch) -> None:
    """serve() writes os.getpid() to .fleetent.pid and removes it on exit."""
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home_dir = tmp_path / "agents" / "test-bot"
    home_dir.mkdir(parents=True)

    pid_during_wait: list[str] = []

    async def capture_pid() -> None:
        pid_file = home_dir / ".fleetent.pid"
        if pid_file.exists():
            pid_during_wait.append(pid_file.read_text().strip())

    rt = MagicMock()
    rt.app = None
    rt.stop = AsyncMock()

    monkeypatch.setattr(agent_app, "boot", AsyncMock(return_value=rt))
    monkeypatch.setattr(agent_app, "_wait_forever", capture_pid)

    await agent_app.serve("test-bot")

    assert len(pid_during_wait) == 1
    assert pid_during_wait[0].isdigit()
    assert not (home_dir / ".fleetent.pid").exists()


async def test_serve_removes_pid_file_on_boot_exception(tmp_path, monkeypatch) -> None:
    """serve() cleans up the PID file even when boot() raises."""
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home_dir = tmp_path / "agents" / "test-bot"
    home_dir.mkdir(parents=True)

    monkeypatch.setattr(agent_app, "boot", AsyncMock(side_effect=RuntimeError("boot failed")))

    with contextlib.suppress(RuntimeError):
        await agent_app.serve("test-bot")

    assert not (home_dir / ".fleetent.pid").exists()


# ── SIGUSR1 graceful drain ────────────────────────────────────────────────────


async def test_serve_drain_on_sigusr1_stops_supervisor_and_exits(tmp_path, monkeypatch) -> None:
    """serve() reacts to SIGUSR1 by calling supervisor.stop_all() then exiting."""
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home_dir = tmp_path / "agents" / "test-bot"
    home_dir.mkdir(parents=True)

    rt = MagicMock()
    rt.app = None
    rt.stop = AsyncMock()

    boot_mock = AsyncMock(return_value=rt)
    monkeypatch.setattr(agent_app, "boot", boot_mock)

    # _wait_forever replaced by a coroutine that sends SIGUSR1 to self mid-run
    async def fire_sigusr1() -> None:
        os.kill(os.getpid(), signal.SIGUSR1)
        await asyncio.sleep(0.2)  # give drain coroutine time to react

    monkeypatch.setattr(agent_app, "_wait_forever", fire_sigusr1)

    await agent_app.serve("test-bot", drain_timeout=1.0)

    rt.stop.assert_awaited()  # supervisor was stopped


# ── _stop_running ─────────────────────────────────────────────────────────────


def test_stop_running_sends_sigusr1(tmp_path, monkeypatch) -> None:
    """_stop_running sends SIGUSR1 to the PID in the pid file."""
    (tmp_path / ".fleetent.pid").write_text("12345")

    kills: list[tuple[int, int]] = []

    def mock_kill(pid: int, sig: int) -> None:
        kills.append((pid, sig))
        if sig == 0:
            raise ProcessLookupError  # process gone after SIGUSR1

    monkeypatch.setattr(os, "kill", mock_kill)

    agent_app._stop_running(tmp_path)

    assert (12345, signal.SIGUSR1) in kills
    assert not (tmp_path / ".fleetent.pid").exists()


def test_stop_running_falls_back_to_sigterm_on_timeout(tmp_path, monkeypatch) -> None:
    """_stop_running sends SIGTERM after drain_timeout expires."""
    (tmp_path / ".fleetent.pid").write_text("12345")

    kills: list[tuple[int, int]] = []
    call_count = [0]

    def mock_kill(pid: int, sig: int) -> None:
        kills.append((pid, sig))
        call_count[0] += 1
        # process only "dies" after SIGTERM (sig 15)
        if sig == 0 and signal.SIGTERM not in [s for _, s in kills]:
            return  # still alive during drain wait
        if sig == 0:
            raise ProcessLookupError  # dead after SIGTERM

    monkeypatch.setattr(os, "kill", mock_kill)
    monkeypatch.setattr(agent_app, "_sleep", lambda s: None)  # skip real sleeps

    agent_app._stop_running(tmp_path, drain_timeout=0.0)

    assert (12345, signal.SIGUSR1) in kills
    assert (12345, signal.SIGTERM) in kills


def test_stop_running_stale_pid_is_silent(tmp_path, monkeypatch) -> None:
    """_stop_running silently succeeds when the process no longer exists."""
    (tmp_path / ".fleetent.pid").write_text("99999")

    def always_fail(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", always_fail)

    agent_app._stop_running(tmp_path)  # must not raise

    assert not (tmp_path / ".fleetent.pid").exists()


def test_stop_running_no_pid_file_is_noop(tmp_path, monkeypatch) -> None:
    """_stop_running does nothing when no pid file exists."""
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kills.append((pid, sig)))

    agent_app._stop_running(tmp_path)

    assert kills == []


# ── restart CLI dispatch ──────────────────────────────────────────────────────


def test_parse_agent_restart_defaults() -> None:
    ns = cli._parse_agent_restart(["my-bot"])
    assert ns.agent_id == "my-bot"
    assert ns.port is None
    assert ns.home is None


def test_parse_agent_restart_with_port_and_home(tmp_path) -> None:
    ns = cli._parse_agent_restart(["my-bot", "--port", "8770", "--home", str(tmp_path)])
    assert ns.port == 8770
    assert ns.home == str(tmp_path)


def test_main_dispatches_agent_restart(tmp_path, monkeypatch) -> None:
    """fleetent agent restart calls _stop_running then asyncio.run(serve(...))."""
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    stop_calls: list[object] = []
    serve_calls: list[str] = []

    monkeypatch.setattr(
        agent_app, "_stop_running", lambda home_dir, **kw: stop_calls.append(home_dir)
    )

    async def fake_serve(agent_id: str, *, port: object = None, home: object = None) -> None:
        serve_calls.append(agent_id)

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "restart", "my-bot"])
    cli.main()

    assert len(stop_calls) == 1
    assert len(serve_calls) == 1
    assert serve_calls[0] == "my-bot"


# ── agent home .env auto-load ─────────────────────────────────────────────────


def _make_mock_agent(name: str = "test-bot") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.mcp_servers = []
    agent.log_format = "console"
    agent.observability.logging.console_level = "info"
    agent.observability.logging.file_level = "debug"
    agent.observability.logging.directory = "data/logs"
    return agent


async def test_boot_loads_dotenv_into_os_environ(tmp_path, monkeypatch) -> None:
    """.env in agent home is loaded into os.environ before scan_home runs."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_DOTENV_SENTINEL=hello-from-dotenv\n")

    monkeypatch.setattr(agent_config, "scan_home", lambda _: _make_mock_agent())
    monkeypatch.setattr(agent_app, "_start_infra", AsyncMock())

    import fleetent.intelligence.vector_store as vs
    import fleetent.skills as skills_mod
    import fleetent.tools.plugin_loader as pl

    monkeypatch.setattr(vs, "configure_from_active_agent", lambda: None)
    monkeypatch.setattr(skills_mod, "scan", lambda skills_dir=None: None)
    monkeypatch.setattr(pl, "load_plugins", lambda: None)

    fake_supervisor = MagicMock()
    fake_supervisor.start = AsyncMock()

    monkeypatch.delenv("TEST_DOTENV_SENTINEL", raising=False)

    await agent_app.boot("test-bot", home=tmp_path, supervisor=fake_supervisor, with_infra=False)

    assert os.environ.get("TEST_DOTENV_SENTINEL") == "hello-from-dotenv"


async def test_boot_silently_skips_missing_dotenv(tmp_path, monkeypatch) -> None:
    """boot() does not raise when no .env file exists in agent home."""
    assert not (tmp_path / ".env").exists()

    monkeypatch.setattr(agent_config, "scan_home", lambda _: _make_mock_agent())
    monkeypatch.setattr(agent_app, "_start_infra", AsyncMock())

    import fleetent.intelligence.vector_store as vs
    import fleetent.skills as skills_mod
    import fleetent.tools.plugin_loader as pl

    monkeypatch.setattr(vs, "configure_from_active_agent", lambda: None)
    monkeypatch.setattr(skills_mod, "scan", lambda skills_dir=None: None)
    monkeypatch.setattr(pl, "load_plugins", lambda: None)

    fake_supervisor = MagicMock()
    fake_supervisor.start = AsyncMock()

    # Should not raise
    await agent_app.boot("test-bot", home=tmp_path, supervisor=fake_supervisor, with_infra=False)


async def test_boot_dotenv_does_not_override_existing_env(tmp_path, monkeypatch) -> None:
    """.env value is ignored when the same var is already in the process environment."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_OVERRIDE_SENTINEL=from-file\n")

    monkeypatch.setenv("TEST_OVERRIDE_SENTINEL", "from-process")

    monkeypatch.setattr(agent_config, "scan_home", lambda _: _make_mock_agent())
    monkeypatch.setattr(agent_app, "_start_infra", AsyncMock())

    import fleetent.intelligence.vector_store as vs
    import fleetent.skills as skills_mod
    import fleetent.tools.plugin_loader as pl

    monkeypatch.setattr(vs, "configure_from_active_agent", lambda: None)
    monkeypatch.setattr(skills_mod, "scan", lambda skills_dir=None: None)
    monkeypatch.setattr(pl, "load_plugins", lambda: None)

    fake_supervisor = MagicMock()
    fake_supervisor.start = AsyncMock()

    await agent_app.boot("test-bot", home=tmp_path, supervisor=fake_supervisor, with_infra=False)

    assert os.environ["TEST_OVERRIDE_SENTINEL"] == "from-process"


def test_pyproject_declares_python_dotenv_directly() -> None:
    """python-dotenv must be a direct dependency, not just a transitive one."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).parent.parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert any("python-dotenv" in d for d in deps), (
        "python-dotenv must be listed in pyproject.toml [project].dependencies"
    )
