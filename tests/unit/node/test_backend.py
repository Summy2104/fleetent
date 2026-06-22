from __future__ import annotations

import os
import subprocess

from fleetent.node.config import NodeConfig


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def test_local_backend_spawn_uses_agent_run(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    calls: list[tuple[tuple[str, ...], str | None, dict[str, str] | None]] = []

    def fake_popen(cmd: list[str], **kwargs):
        calls.append((tuple(cmd), kwargs.get("cwd"), kwargs.get("env")))
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("BASE_ENV", "base-value")

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support", env={"ANTHROPIC_API_KEY": "sk-live-secret"})

    assert len(calls) == 1
    cmd, cwd, env = calls[0]
    assigned_port = backend.gateway_port("support")
    assert assigned_port is not None
    assert cmd == (
        "fleetent",
        "agent",
        "run",
        "support",
        "--port",
        str(assigned_port),
        "--home",
        str(tmp_path / "agents" / "support"),
    )
    assert cwd == str(tmp_path)
    assert env is not None
    assert env["BASE_ENV"] == "base-value"
    assert env["ANTHROPIC_API_KEY"] == "sk-live-secret"
    assert not (tmp_path / "agents" / "support" / ".env").exists()


def test_local_backend_stop_uses_agent_stop(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append((tuple(cmd), kwargs["check"]))
        return object()

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.stop("support")

    assert calls == [
        (
            (
                "fleetent",
                "agent",
                "stop",
                "support",
                "--home",
                str(tmp_path / "agents" / "support"),
            ),
            True,
        )
    ]


def test_local_backend_is_alive_reads_pid_file_and_checks_process(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kills.append((pid, sig)))

    backend = LocalProcessBackend(_config(tmp_path))

    assert backend.is_alive("support") == 12345
    assert kills == [(12345, 0)]


def test_local_backend_is_alive_returns_none_for_stale_pid(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    def fake_kill(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", fake_kill)

    backend = LocalProcessBackend(_config(tmp_path))

    assert backend.is_alive("support") is None
