"""Structural tests for the Docker backend migration (sandbox-backend-abstraction).

`client.py` becomes a re-export shim; the real implementation is
`backends/docker.py::DockerBackend`, which subclasses the abstraction and declares
the full (all-true) capability set.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.integrations.sandbox.backend import BaseSandboxBackend
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.client import SandboxClient


def _mock_proc(returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(b"", b""))
    return proc


def test_docker_backend_subclasses_abstraction() -> None:
    assert issubclass(DockerBackend, BaseSandboxBackend)
    assert DockerBackend.name == "docker"


def test_docker_backend_declares_full_capabilities() -> None:
    caps = DockerBackend.capabilities
    assert caps.persist_workspace is True
    assert caps.workspace_mount is True
    assert caps.orphan_cleanup is True


def test_client_shim_aliases_docker_backend() -> None:
    # The legacy import path resolves to the Docker backend (behaviour unchanged).
    assert SandboxClient is DockerBackend


async def test_available_true_on_zero_returncode() -> None:
    backend = DockerBackend()
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(0))):
        assert await backend.available() is True


async def test_available_false_when_cli_missing() -> None:
    backend = DockerBackend()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError("docker"))
    ):
        assert await backend.available() is False
