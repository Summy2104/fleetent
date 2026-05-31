"""Tests for SandboxClient (Docker-backed implementation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.sandbox_client import SandboxClient
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
        ws_id = await client.create_workspace("sandbox-session-1", resources=SandboxResources())
    assert ws_id == "abc123def456"


async def test_create_workspace_raises_on_docker_failure(client):
    mock_proc = _mock_proc(stderr="image not found", returncode=125)
    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
        pytest.raises(RuntimeError, match="docker run failed"),
    ):
        await client.create_workspace("sandbox-session-bad", resources=SandboxResources())


async def test_create_workspace_uses_name_verbatim(client):
    """The container name is taken from the `name` arg as-is (sanitisation is the
    caller/manager's job under the converged signature), not derived here."""
    argv = await _capture_create_workspace(client, name="sandbox-session-already-safe")
    assert argv[argv.index("--name") + 1] == "sandbox-session-already-safe"


async def test_create_workspace_uses_image_arg(client):
    """An explicit `image` overrides the client default base image in docker run."""
    argv = await _capture_create_workspace(client, image="fleetent-sandbox-agent-bot:latest")
    assert "fleetent-sandbox-agent-bot:latest" in argv
    assert "python:3.12-slim" not in argv


async def test_create_workspace_image_none_uses_client_default(client):
    """image=None falls back to the client's default base image."""
    argv = await _capture_create_workspace(client, image=None)
    assert "python:3.12-slim" in argv


async def test_find_workspace_returns_id_when_present(client):
    """docker ps -q --filter name=... yields the container id when one matches."""
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc(stdout="abc123\n")

    with patch("asyncio.create_subprocess_exec", fake_exec):
        ws_id = await client.find_workspace("sandbox-session-1")

    assert ws_id == "abc123"
    assert captured[0][:2] == ["docker", "ps"]
    assert "name=^sandbox-session-1$" in captured[0]


async def test_find_workspace_returns_none_when_absent(client):
    """Empty docker ps output means no matching container -> None."""
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(stdout="\n"))):
        ws_id = await client.find_workspace("sandbox-session-missing")
    assert ws_id is None


async def test_commit_workspace_calls_docker_commit(client):
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc(stdout="sha256:deadbeef\n")

    with patch("asyncio.create_subprocess_exec", fake_exec):
        await client.commit_workspace("container-xyz", "fleetent-sandbox-agent-bot:latest")

    assert captured[0][:2] == ["docker", "commit"]
    assert "container-xyz" in captured[0]
    assert "fleetent-sandbox-agent-bot:latest" in captured[0]


async def test_commit_workspace_raises_on_failure(client):
    mock_proc = _mock_proc(stderr="no such container", returncode=1)
    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
        pytest.raises(RuntimeError, match="docker commit failed"),
    ):
        await client.commit_workspace("gone", "tag:latest")


async def test_image_exists_true_when_inspect_succeeds(client):
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(returncode=0))):
        assert await client.image_exists("fleetent-sandbox-agent-bot:latest") is True


async def test_image_exists_false_when_inspect_fails(client):
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(returncode=1))):
        assert await client.image_exists("fleetent-sandbox-agent-bot:latest") is False


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
    client: SandboxClient,
    *,
    resources: SandboxResources | None = None,
    name: str = "sandbox-session-1",
    image: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Run create_workspace under a mocked subprocess and return the argv."""
    captured: list[list[str]] = []

    async def fake_exec(*args, **kwargs):
        captured.append(list(args))
        return _mock_proc(stdout="cid\n")

    with patch("asyncio.create_subprocess_exec", fake_exec):
        await client.create_workspace(
            name, resources=resources or SandboxResources(), image=image, env=env
        )
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


async def test_create_workspace_injects_env_as_e_flag(client):
    """env entries become `-e KEY=VALUE` on docker run (SB5 D3)."""
    argv = await _capture_create_workspace(client, env={"DATA_DIR": "/x"})
    e_idxs = [i for i, a in enumerate(argv) if a == "-e"]
    values = [argv[i + 1] for i in e_idxs]
    assert "DATA_DIR=/x" in values


async def test_create_workspace_env_none_omits_e_flag(client):
    """env=None reproduces current behaviour: no -e flags."""
    argv = await _capture_create_workspace(client, env=None)
    assert "-e" not in argv


async def test_create_workspace_env_empty_omits_e_flag(client):
    """An empty env mapping equally adds no -e flags."""
    argv = await _capture_create_workspace(client, env={})
    assert "-e" not in argv


async def test_create_workspace_defensive_filters_sensitive_env(client):
    """Even if a caller mistakenly passes a sensitive-named var, it is dropped
    before docker run (SB5 D3 defence-in-depth — do not trust the caller)."""
    argv = await _capture_create_workspace(
        client, env={"MY_TOKEN": "leak", "DB_PASSWORD": "leak", "DATA_DIR": "/x"}
    )
    joined = " ".join(argv)
    assert "MY_TOKEN" not in joined
    assert "DB_PASSWORD" not in joined
    assert "leak" not in joined
    e_idxs = [i for i, a in enumerate(argv) if a == "-e"]
    assert [argv[i + 1] for i in e_idxs] == ["DATA_DIR=/x"]
