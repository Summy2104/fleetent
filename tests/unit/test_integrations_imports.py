"""Import tests for canonical integrations packages."""

from __future__ import annotations

import importlib


def test_integrations_packages_are_importable() -> None:
    assert importlib.import_module("fleetent.integrations")
    assert importlib.import_module("fleetent.integrations.mcp")
    assert importlib.import_module("fleetent.integrations.mcp.client")
    assert importlib.import_module("fleetent.integrations.sandbox")
    assert importlib.import_module("fleetent.integrations.sandbox.client")


def test_mcp_canonical_path_exports_public_api() -> None:
    canonical = importlib.import_module("fleetent.integrations.mcp")
    client = importlib.import_module("fleetent.integrations.mcp.client")

    for name in ("McpServerConfig", "register_all", "close", "call_tool"):
        assert getattr(canonical, name) is getattr(client, name)


def test_sandbox_canonical_path_exports_public_api() -> None:
    canonical = importlib.import_module("fleetent.integrations.sandbox")
    client = importlib.import_module("fleetent.integrations.sandbox.client")

    for name in ("SandboxClient", "ExecResult"):
        assert getattr(canonical, name) is getattr(client, name)
