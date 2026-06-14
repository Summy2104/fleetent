"""Sandbox backend factory (sandbox-backend-abstraction).

Resolves which backend to instantiate from configuration, with precedence
``agent.yaml`` override > ``platform.yaml`` default > ``docker``. An invalid
backend name (from either source) logs a warning and falls back to docker rather
than being silently accepted. The microsandbox backend is imported lazily inside
its branch so a docker-only deployment never loads the microsandbox package.
"""

from __future__ import annotations

from pathlib import Path

from fleetent.agent_config import AgentFile
from fleetent.integrations.sandbox.backend import BaseSandboxBackend
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.config import (
    _DEFAULT_BACKEND,
    _VALID_BACKENDS,
    load_sandbox_backend_config,
)
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.factory")


def create_backend(
    agent: AgentFile | None = None, *, platform_path: Path | None = None
) -> BaseSandboxBackend:
    """Return the configured sandbox backend instance.

    `agent` (when given) supplies the per-agent `sandbox` override; `platform_path`
    points at the platform settings file (defaults to the standard location). Backend
    selection precedence: agent override > platform default > docker. The microsandbox
    base image is resolved with the same precedence.
    """
    platform_cfg = load_sandbox_backend_config(platform_path)
    name = platform_cfg.backend
    image = platform_cfg.microsandbox_image
    docker_image = platform_cfg.docker_image

    if agent is not None:
        agent_sandbox = agent.sandbox
        if agent_sandbox.backend is not None:
            if agent_sandbox.backend in _VALID_BACKENDS:
                name = agent_sandbox.backend
            else:
                _logger.warn(
                    "sandbox_backend_invalid",
                    value=agent_sandbox.backend,
                    falling_back=_DEFAULT_BACKEND,
                )
                name = _DEFAULT_BACKEND
        if agent_sandbox.microsandbox.image:
            image = agent_sandbox.microsandbox.image
        if agent_sandbox.docker.image:
            docker_image = agent_sandbox.docker.image

    if name == "microsandbox":
        # Lazy import: a docker-only deployment never loads the microsandbox backend.
        from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend

        return MicrosandboxBackend(image=image) if image else MicrosandboxBackend()
    return DockerBackend(image=docker_image) if docker_image else DockerBackend()
