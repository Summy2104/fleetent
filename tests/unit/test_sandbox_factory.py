"""Backend factory selection + precedence (sandbox-backend-abstraction).

Pure config→backend resolution: agent.yaml override > platform.yaml > docker default.
No DB / service, so this stays a unit test.
"""

from __future__ import annotations

from pathlib import Path

from fleetent.agent_config import AgentFile, default_models
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend
from fleetent.integrations.sandbox.factory import create_backend


def _agent(backend: str | None = None, image: str | None = None) -> AgentFile:
    sandbox: dict = {}
    if backend is not None:
        sandbox["backend"] = backend
    if image is not None:
        sandbox["microsandbox"] = {"image": image}
    kwargs = {"name": "a", "version": 1, "models": default_models()}
    if sandbox:
        kwargs["sandbox"] = sandbox
    return AgentFile(**kwargs)


def _platform(tmp_path: Path, backend: str | None = None) -> Path:
    p = tmp_path / "platform.yaml"
    p.write_text(f"sandbox:\n  backend: {backend}\n" if backend else "other: {}\n")
    return p


def test_default_is_docker(tmp_path: Path) -> None:
    backend = create_backend(platform_path=tmp_path / "missing.yaml")
    assert isinstance(backend, DockerBackend)


def test_platform_microsandbox_selected(tmp_path: Path) -> None:
    backend = create_backend(platform_path=_platform(tmp_path, "microsandbox"))
    assert isinstance(backend, MicrosandboxBackend)


def test_agent_override_beats_platform_docker(tmp_path: Path) -> None:
    backend = create_backend(_agent("microsandbox"), platform_path=_platform(tmp_path, "docker"))
    assert isinstance(backend, MicrosandboxBackend)


def test_agent_docker_beats_platform_microsandbox(tmp_path: Path) -> None:
    backend = create_backend(_agent("docker"), platform_path=_platform(tmp_path, "microsandbox"))
    assert isinstance(backend, DockerBackend)


def test_agent_none_inherits_platform(tmp_path: Path) -> None:
    backend = create_backend(_agent(None), platform_path=_platform(tmp_path, "microsandbox"))
    assert isinstance(backend, MicrosandboxBackend)


def test_invalid_agent_backend_falls_back_to_docker(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("fleetent.integrations.sandbox.factory._logger") as mock_log:
        backend = create_backend(_agent("firecracker"), platform_path=tmp_path / "missing.yaml")
    assert isinstance(backend, DockerBackend)
    mock_log.warn.assert_called()


def test_microsandbox_image_from_agent(tmp_path: Path) -> None:
    backend = create_backend(_agent("microsandbox", image="alpine"))
    assert isinstance(backend, MicrosandboxBackend)
    assert backend._image == "alpine"


def test_docker_selection_does_not_require_microsandbox(tmp_path: Path) -> None:
    """Selecting docker must not import the microsandbox package (lazy isolation)."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "microsandbox":
            raise AssertionError("microsandbox must not be imported for the docker backend")
        return real_import(name, *a, **k)

    from unittest.mock import patch

    with patch("builtins.__import__", side_effect=fake_import):
        backend = create_backend(platform_path=tmp_path / "missing.yaml")
    assert isinstance(backend, DockerBackend)
