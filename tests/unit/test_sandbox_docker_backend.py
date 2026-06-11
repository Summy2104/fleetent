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


# --- container-missing error classification (sandbox-liveness-reacquire) ----


def test_is_workspace_missing_detects_dead_container() -> None:
    from fleetent.integrations.sandbox.backend import ExecResult
    from fleetent.integrations.sandbox.backends.docker import DockerBackend

    dead = ExecResult("", "Error response from daemon: No such container: 0d22badd11c4", 1)
    assert DockerBackend().is_workspace_missing(dead) is True


def test_is_workspace_missing_detects_not_running() -> None:
    from fleetent.integrations.sandbox.backend import ExecResult
    from fleetent.integrations.sandbox.backends.docker import DockerBackend

    stopped = ExecResult("", "Error response from daemon: container abc is not running", 1)
    assert DockerBackend().is_workspace_missing(stopped) is True


def test_is_workspace_missing_false_on_ordinary_command_failure() -> None:
    from fleetent.integrations.sandbox.backend import ExecResult
    from fleetent.integrations.sandbox.backends.docker import DockerBackend

    res = ExecResult("", "ls: cannot access '/x': No such file or directory", 2)
    assert DockerBackend().is_workspace_missing(res) is False


# --- declarative offline build of an immutable deps image (image-persistence) ---


async def test_build_deps_image_builds_offline_from_setup_command() -> None:
    """build_deps_image runs `docker build` over a Dockerfile that layers the declared
    setup_command on top of the base image — an offline build, never a commit of a
    running container that executed end-user code."""
    backend = DockerBackend()
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["stdin"] = kwargs.get("stdin")
        return _mock_proc(0)

    with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=fake_exec)):
        await backend.build_deps_image(
            image_tag="fleetent-sandbox-deps-bot:latest",
            setup_command="pip install requests",
            base_image="python:3.12-slim",
        )
    args = captured["args"]
    assert args[0] == "docker"
    assert "build" in args
    # tagged with the immutable deps image tag
    assert "fleetent-sandbox-deps-bot:latest" in args
    # the build never references a running container id (no `commit`)
    assert "commit" not in args


async def test_build_deps_image_raises_on_nonzero() -> None:
    backend = DockerBackend()
    proc = MagicMock()
    proc.returncode = 1
    proc.communicate = AsyncMock(return_value=(b"", b"build failed"))
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        try:
            await backend.build_deps_image(
                image_tag="t:latest",
                setup_command="bad",
                base_image="python:3.12-slim",
            )
        except RuntimeError as exc:
            assert "build" in str(exc).lower()
        else:
            raise AssertionError("expected RuntimeError on non-zero build")


async def test_base_backend_build_deps_image_default_unsupported() -> None:
    """A backend without persist_workspace must not silently 'build' — the base default
    raises NotImplementedError (callers gate on the capability before calling)."""
    import pytest

    from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend

    backend = MicrosandboxBackend()
    with pytest.raises(NotImplementedError):
        await backend.build_deps_image(image_tag="t", setup_command="x", base_image="y")
