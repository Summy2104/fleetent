"""Tests for SandboxClient (Docker-backed implementation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.sandbox_client import ExecResult, SandboxClient
from fleetent.sandbox_config import NetworkPolicy, SandboxResources


def _mock_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    return proc


@pytest.fixture
def client():
    return SandboxClient(image="python:3.12-slim")


async def test_create_workspace_returns_container_id(client):
    fake_id = "abc123def456\n"
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(stdout=fake_id))
    ):
        ws_id = await client.create_workspace("session-1")
    assert ws_id == "abc123def456"


async def test_create_workspace_raises_on_docker_failure(client):
    mock_proc = _mock_proc(stderr="image not found", returncode=125)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(RuntimeError, match="docker run failed"):
            await client.create_workspace("session-bad")


async def test_create_workspace_sanitizes_session_id(client):
    """Special characters in session_id are replaced with dashes in container name."""
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc(stdout="cid\n")

    with patch("asyncio.create_subprocess_exec", fake_exec):
        await client.create_workspace("user:U123/channel#abc")

    name_arg = captured[0][captured[0].index("--name") + 1]
    assert ":" not in name_arg
    assert "/" not in name_arg
    assert "#" not in name_arg


async def test_exec_returns_result(client):
    mock_proc = _mock_proc(stdout="hello\n", stderr="", returncode=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await client.exec("container-id", "echo hello")
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.exit_code == 0


async def test_exec_non_zero_exit_does_not_raise(client):
    mock_proc = _mock_proc(stdout="", stderr="No such file", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await client.exec("container-id", "false")
    assert result.exit_code == 1
    assert result.stderr == "No such file"


async def test_destroy_workspace_calls_docker_rm(client):
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc()

    with patch("asyncio.create_subprocess_exec", fake_exec):
        await client.destroy_workspace("container-abc")

    assert captured[0][:4] == ["docker", "rm", "-f", "container-abc"]


async def test_destroy_workspace_is_idempotent_when_container_absent(client):
    """A second destroy (container already gone / rm -f already ran) must not raise."""
    # docker rm -f on a missing container exits non-zero; destroy_workspace must
    # swallow that so the cancel path's destroy + finally's fallback destroy
    # cannot double-raise (AR19 D3b).
    mock_proc = _mock_proc(stderr="Error: No such container: gone", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await client.destroy_workspace("already-gone")
        await client.destroy_workspace("already-gone")


async def test_docker_available_true_on_zero_returncode(client):
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(returncode=0))):
        assert await client.docker_available() is True


async def test_docker_available_false_on_nonzero_returncode(client):
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(returncode=1))):
        assert await client.docker_available() is False


async def test_docker_available_false_when_cli_missing(client):
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError("docker"))
    ):
        assert await client.docker_available() is False


async def _capture_create_workspace(
    client: SandboxClient, *, resources: SandboxResources | None = None
) -> list[str]:
    """Run create_workspace under a mocked subprocess and return the argv."""
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc(stdout="cid\n")

    with patch("asyncio.create_subprocess_exec", fake_exec):
        if resources is None:
            await client.create_workspace("session-1")
        else:
            await client.create_workspace("session-1", resources=resources)
    return captured[0]


async def test_create_workspace_maps_memory_and_cpus(client):
    res = SandboxResources(memory=1024, cpus=2.0)
    argv = await _capture_create_workspace(client, resources=res)
    assert argv[argv.index("--memory") + 1] == "1024m"
    assert argv[argv.index("--cpus") + 1] == "2.0"


async def test_create_workspace_network_none_adds_network_none(client):
    res = SandboxResources(network=NetworkPolicy.NONE)
    argv = await _capture_create_workspace(client, resources=res)
    assert argv[argv.index("--network") + 1] == "none"


async def test_create_workspace_allow_all_omits_network_flag(client):
    res = SandboxResources(network=NetworkPolicy.ALLOW_ALL)
    argv = await _capture_create_workspace(client, resources=res)
    assert "--network" not in argv


async def test_create_workspace_public_only_falls_back_to_none(client):
    """public_only network is not provisioned, so it degrades to --network none
    rather than silently allowing the default bridge."""
    res = SandboxResources(network=NetworkPolicy.PUBLIC_ONLY)
    argv = await _capture_create_workspace(client, resources=res)
    assert argv[argv.index("--network") + 1] == "none"


async def test_create_workspace_read_only_true_adds_flag(client):
    res = SandboxResources(read_only=True)
    argv = await _capture_create_workspace(client, resources=res)
    assert "--read-only" in argv


async def test_create_workspace_read_only_false_omits_flag(client):
    res = SandboxResources(read_only=False)
    argv = await _capture_create_workspace(client, resources=res)
    assert "--read-only" not in argv


async def test_create_workspace_always_keeps_tmpfs(client):
    res = SandboxResources(read_only=False, network=NetworkPolicy.ALLOW_ALL)
    argv = await _capture_create_workspace(client, resources=res)
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"


async def test_create_workspace_exec_timeout_not_in_docker_run(client):
    """exec_timeout is carried for wave-3 only; it must not reach docker run."""
    res = SandboxResources(exec_timeout=120)
    argv = await _capture_create_workspace(client, resources=res)
    assert "120" not in argv
    assert "--stop-timeout" not in argv


async def test_create_workspace_per_scope_does_not_bleed(client):
    """The same client builds read-only then writable containers independently."""
    read_only = await _capture_create_workspace(client, resources=SandboxResources(read_only=True))
    writable = await _capture_create_workspace(client, resources=SandboxResources(read_only=False))
    assert "--read-only" in read_only
    assert "--read-only" not in writable


async def test_create_workspace_default_command_matches_current_behaviour(client):
    """No resources arg reproduces the pre-SB4 hardcoded command exactly."""
    argv = await _capture_create_workspace(client)
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--memory") + 1] == "256m"
    assert argv[argv.index("--cpus") + 1] == "0.5"
    assert "--read-only" in argv
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"
