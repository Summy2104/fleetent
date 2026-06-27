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


def _config_with_backend(tmp_path, backend: str) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
        backend=backend,
    )


def _container_config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
        backend="container",
        agent_image="fleetent:test",
        agent_network="fleetent-net",
        agent_internal_port=18765,
    )


def _home(tmp_path, agent_name: str = "support", tenant_id: str = "default"):
    return tmp_path / "tenants" / tenant_id / "agents" / agent_name


class _FakePopen:
    returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode


def test_local_backend_spawn_uses_agent_run(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    calls: list[tuple[tuple[str, ...], str | None]] = []

    def fake_popen(cmd: list[str], **kwargs):
        calls.append((tuple(cmd), kwargs.get("cwd")))
        return _FakePopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")

    assert len(calls) == 1
    cmd, cwd = calls[0]
    assigned_port = backend.gateway_port("support")
    assert assigned_port is not None
    assert cmd == (
        "fleetent",
        "agent",
        "run",
        "support",
        "--no-im",
        "--port",
        str(assigned_port),
        "--home",
        str(_home(tmp_path)),
    )
    assert cwd == str(tmp_path)


def test_create_process_backend_defaults_to_local_process_backend(tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend, create_process_backend

    backend = create_process_backend(_config(tmp_path))

    assert isinstance(backend, LocalProcessBackend)


def test_create_process_backend_selects_container_backend(tmp_path) -> None:
    from fleetent.node.backend import ContainerBackend, create_process_backend

    backend = create_process_backend(_config_with_backend(tmp_path, "container"))

    assert isinstance(backend, ContainerBackend)


def test_local_backend_agent_endpoint_returns_loopback_and_gateway_port(tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    backend = LocalProcessBackend(_config(tmp_path))
    backend._gateway_ports["support"] = 9011

    assert backend.agent_endpoint("support", "tenant-1") == ("127.0.0.1", 9011)


def test_local_backend_spawn_disables_agent_local_im(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    calls: list[tuple[str, ...]] = []

    def fake_popen(cmd: list[str], **kwargs):
        calls.append(tuple(cmd))
        return _FakePopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")

    assert "--no-im" in calls[0]


def test_container_backend_spawn_runs_agent_container_with_labels_network_and_mounts(
    monkeypatch, tmp_path
) -> None:
    from fleetent.node.backend import ContainerBackend

    calls: list[tuple[str, ...]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = ContainerBackend(_container_config(tmp_path))
    backend.spawn("support", "tenant-1")

    assert calls == [
        (
            "docker",
            "run",
            "-d",
            "--name",
            "fleetent-agent-tenant-1-support",
            "--label",
            "fleetent.role=agent",
            "--label",
            "fleetent.agent.name=support",
            "--label",
            "fleetent.agent.tenant=tenant-1",
            "--network",
            "fleetent-net",
            "--mount",
            f"type=bind,source={tmp_path / 'tenants/tenant-1/agents/support'},"
            f"target={tmp_path / 'tenants/tenant-1/agents/support'},readonly=false",
            "--mount",
            f"type=bind,source={tmp_path / 'tenants/tenant-1/kb.db'},"
            f"target={tmp_path / 'tenants/tenant-1/kb.db'},readonly=true",
            "--mount",
            f"type=bind,source={tmp_path / 'tenants/tenant-1/kb_vectors.db'},"
            f"target={tmp_path / 'tenants/tenant-1/kb_vectors.db'},readonly=true",
            "fleetent:test",
            "fleetent",
            "agent",
            "run",
            "support",
            "--no-im",
            "--port",
            "18765",
            "--home",
            str(tmp_path / "tenants/tenant-1/agents/support"),
        )
    ]


def test_container_backend_is_alive_uses_label_filtered_running_container(
    monkeypatch, tmp_path
) -> None:
    from fleetent.node.backend import ContainerBackend

    calls: list[tuple[str, ...]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = ContainerBackend(_container_config(tmp_path))

    assert backend.is_alive("support", "tenant-1") == 1
    assert calls == [
        (
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=fleetent.role=agent",
            "--filter",
            "label=fleetent.agent.name=support",
            "--filter",
            "label=fleetent.agent.tenant=tenant-1",
            "--filter",
            "status=running",
        )
    ]


def test_container_backend_is_alive_returns_none_when_no_running_container(
    monkeypatch, tmp_path
) -> None:
    from fleetent.node.backend import ContainerBackend

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )

    backend = ContainerBackend(_container_config(tmp_path))

    assert backend.is_alive("support", "tenant-1") is None


def test_container_backend_stop_execs_agent_stop(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import ContainerBackend

    calls: list[tuple[str, ...]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = ContainerBackend(_container_config(tmp_path))
    backend.stop("support", "tenant-1")

    assert calls == [
        (
            "docker",
            "exec",
            "fleetent-agent-tenant-1-support",
            "fleetent",
            "agent",
            "stop",
            "support",
            "--home",
            str(tmp_path / "tenants/tenant-1/agents/support"),
        )
    ]


def test_container_backend_stop_falls_back_to_docker_stop(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import ContainerBackend

    calls: list[tuple[str, ...]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(tuple(cmd))
        if cmd[:2] == ["docker", "exec"]:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = ContainerBackend(_container_config(tmp_path))
    backend.stop("support", "tenant-1")

    assert calls == [
        (
            "docker",
            "exec",
            "fleetent-agent-tenant-1-support",
            "fleetent",
            "agent",
            "stop",
            "support",
            "--home",
            str(tmp_path / "tenants/tenant-1/agents/support"),
        ),
        ("docker", "stop", "fleetent-agent-tenant-1-support"),
    ]


def test_container_backend_agent_endpoint_returns_container_name_and_internal_port(
    tmp_path,
) -> None:
    from fleetent.node.backend import ContainerBackend

    backend = ContainerBackend(_container_config(tmp_path))

    assert backend.agent_endpoint("support", "tenant-1") == (
        "fleetent-agent-tenant-1-support",
        18765,
    )


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
                str(_home(tmp_path)),
            ),
            True,
        )
    ]


def test_local_backend_stop_removes_spawned_process_handle(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    proc = _FakePopen()
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: proc)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: object())

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")
    backend.stop("support")

    assert "support" not in backend._procs


def test_local_backend_is_alive_reads_pid_file_and_checks_process(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kills.append((pid, sig)))

    backend = LocalProcessBackend(_config(tmp_path))

    assert backend.is_alive("support") == 12345
    assert kills == [(12345, 0)]


def test_local_backend_is_alive_returns_none_for_stale_pid(monkeypatch, tmp_path) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    def fake_kill(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", fake_kill)

    backend = LocalProcessBackend(_config(tmp_path))

    assert backend.is_alive("support") is None


def test_local_backend_is_alive_returns_none_for_exited_spawned_child(
    monkeypatch, tmp_path
) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    proc = _FakePopen()
    proc.returncode = -9
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: proc)
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")

    assert backend.is_alive("support") is None


def test_local_backend_is_alive_prefers_spawned_child_returncode_over_os_kill(
    monkeypatch, tmp_path
) -> None:
    from fleetent.node.backend import LocalProcessBackend

    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".fleetent.pid").write_text("12345")

    proc = _FakePopen()
    proc.returncode = 1
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: proc)

    def fake_kill(pid: int, sig: int) -> None:
        raise AssertionError("os.kill should not be consulted after the child exited")

    monkeypatch.setattr(os, "kill", fake_kill)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")

    assert backend.is_alive("support") is None


# --- task 2.4: spawn must NOT inject secrets via process env ---


def test_local_backend_spawn_does_not_inject_secrets_in_process_env(monkeypatch, tmp_path) -> None:
    """After D1 (env-only), secrets live in .env only; spawn must not pass env to Popen."""
    from fleetent.node.backend import LocalProcessBackend

    popen_kwargs: list[dict] = []

    def fake_popen(cmd: list[str], **kwargs):
        popen_kwargs.append(kwargs)
        return _FakePopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    backend = LocalProcessBackend(_config(tmp_path))
    backend.spawn("support")

    assert len(popen_kwargs) == 1
    # env=None means Popen inherits the parent env; no injected secret dict
    assert popen_kwargs[0].get("env") is None
