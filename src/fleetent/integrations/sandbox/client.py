"""Legacy import shim for the Docker sandbox backend.

The Docker implementation moved to ``backends/docker.py`` under the pluggable
backend abstraction (sandbox-backend-abstraction). This module preserves the
historical import surface — ``SandboxClient`` (now an alias for ``DockerBackend``),
``ExecResult``, ``SANDBOX_NAME_PREFIX`` and ``_SAFE_NAME`` — so existing callers
keep working. New code should depend on `BaseSandboxBackend` / the factory, not on
this Docker-specific name.

NOTE: ``monkeypatch``/``patch`` targets for Docker internals (e.g.
``_KILL_GRACE_SECONDS``) must point at ``backends.docker`` — re-exports here are
copies of references, so patching the shim does not affect the real module.
"""

from __future__ import annotations

from fleetent.integrations.sandbox.backend import (
    _SAFE_NAME,
    SANDBOX_NAME_PREFIX,
    BackendCapabilities,
    BaseSandboxBackend,
    ExecResult,
)
from fleetent.integrations.sandbox.backends.docker import DockerBackend

# Legacy alias: the canonical Docker backend was historically named SandboxClient.
SandboxClient = DockerBackend

__all__ = [
    "SANDBOX_NAME_PREFIX",
    "BackendCapabilities",
    "BaseSandboxBackend",
    "DockerBackend",
    "ExecResult",
    "SandboxClient",
    "_SAFE_NAME",
]
