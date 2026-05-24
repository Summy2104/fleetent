"""Tests for SandboxClient (Docker-backed implementation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_agent.sandbox_client import ExecResult, SandboxClient


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
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(stdout=fake_id))):
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
