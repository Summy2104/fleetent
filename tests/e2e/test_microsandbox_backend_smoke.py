"""Real-microVM smoke test for the microsandbox backend (microsandbox-backend).

Opt-in and environment-gated: requires `FLEETENT_RUN_E2E=1`, the microsandbox runtime
installed, and host hardware virtualization (Linux KVM / macOS HVF). Never part of the
PR gate — it boots a real microVM. Exercises the full create -> exec -> destroy path
through the backend abstraction (no Docker involved).
"""

from __future__ import annotations

import os

import pytest

from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend
from fleetent.integrations.sandbox.config import SandboxResources

pytestmark = pytest.mark.skipif(
    os.getenv("FLEETENT_RUN_E2E") != "1",
    reason="set FLEETENT_RUN_E2E=1 (and install the microsandbox runtime) to run microVM smoke",
)


async def _require_runtime(backend: MicrosandboxBackend) -> None:
    if not await backend.available():
        pytest.skip("microsandbox runtime not installed / virtualization unavailable")


async def test_create_exec_destroy_roundtrip() -> None:
    backend = MicrosandboxBackend()
    await _require_runtime(backend)
    name = "sandbox-e2e-smoke"
    ws = await backend.create_workspace(name, resources=SandboxResources())
    try:
        result = await backend.exec(ws, "echo hello-microvm")
        assert result.exit_code == 0
        assert "hello-microvm" in result.stdout
    finally:
        await backend.destroy_workspace(ws)


async def test_session_continuity_persists_env() -> None:
    backend = MicrosandboxBackend()
    await _require_runtime(backend)
    name = "sandbox-e2e-continuity"
    ws = await backend.create_workspace(name, resources=SandboxResources())
    try:
        await backend.exec(ws, "export FOO=bar", session_id="s1")
        result = await backend.exec(ws, "echo $FOO", session_id="s1")
        assert "bar" in result.stdout
    finally:
        await backend.destroy_workspace(ws)
