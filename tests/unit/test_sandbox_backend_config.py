"""Config parsing for sandbox backend selection (sandbox-backend-abstraction)."""

from __future__ import annotations

from pathlib import Path

from fleetent.agent_config import AgentFile, default_models
from fleetent.integrations.sandbox.config import load_sandbox_backend_config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "platform.yaml"
    p.write_text(body)
    return p


def test_backend_defaults_to_docker_when_file_absent(tmp_path: Path) -> None:
    cfg = load_sandbox_backend_config(tmp_path / "missing.yaml")
    assert cfg.backend == "docker"
    assert cfg.microsandbox_image is None


def test_backend_defaults_to_docker_when_section_absent(tmp_path: Path) -> None:
    cfg = load_sandbox_backend_config(_write(tmp_path, "other: {}\n"))
    assert cfg.backend == "docker"


def test_backend_reads_microsandbox(tmp_path: Path) -> None:
    cfg = load_sandbox_backend_config(
        _write(
            tmp_path, "sandbox:\n  backend: microsandbox\n  microsandbox:\n    image: python:3.12\n"
        )
    )
    assert cfg.backend == "microsandbox"
    assert cfg.microsandbox_image == "python:3.12"


def test_invalid_backend_falls_back_to_docker_with_warning(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("fleetent.integrations.sandbox.config._logger") as mock_log:
        cfg = load_sandbox_backend_config(_write(tmp_path, "sandbox:\n  backend: firecracker\n"))
    assert cfg.backend == "docker"
    mock_log.warn.assert_called()


def test_agent_file_sandbox_section_defaults() -> None:
    af = AgentFile(name="a", version=1, models=default_models())
    # No sandbox section declared -> backend inherits (None), microsandbox image None.
    assert af.sandbox.backend is None
    assert af.sandbox.microsandbox.image is None


def test_agent_file_sandbox_section_parsed() -> None:
    af = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        sandbox={"backend": "microsandbox", "microsandbox": {"image": "alpine"}},
    )
    assert af.sandbox.backend == "microsandbox"
    assert af.sandbox.microsandbox.image == "alpine"
