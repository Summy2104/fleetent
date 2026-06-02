"""Import compatibility tests for integrations package migration."""

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


def test_mcp_legacy_path_reexports_canonical_objects() -> None:
    legacy = importlib.import_module("fleetent.mcp_client")
    client = importlib.import_module("fleetent.integrations.mcp.client")

    for name in (
        "McpServerConfig",
        "register_all",
        "close",
        "call_tool",
        "_make_tool_name",
        "_register_server",
        "_register_tool_http",
    ):
        assert getattr(legacy, name) is getattr(client, name)


def test_mcp_legacy_path_shares_canonical_registry_state(monkeypatch) -> None:
    legacy = importlib.import_module("fleetent.mcp_client")
    client = importlib.import_module("fleetent.integrations.mcp.client")

    assert legacy._server_registry is client._server_registry
    server = client.McpServerConfig(id="compat", url="http://compat.test")
    monkeypatch.setitem(client._server_registry, "compat", server)

    assert legacy._server_registry["compat"] is server


def test_sandbox_canonical_path_exports_public_api() -> None:
    canonical = importlib.import_module("fleetent.integrations.sandbox")
    client = importlib.import_module("fleetent.integrations.sandbox.client")

    for name in ("SandboxClient", "ExecResult"):
        assert getattr(canonical, name) is getattr(client, name)


def test_sandbox_legacy_path_reexports_canonical_objects() -> None:
    legacy = importlib.import_module("fleetent.sandbox_client")
    client = importlib.import_module("fleetent.integrations.sandbox.client")

    assert legacy.SandboxClient is client.SandboxClient
    assert legacy.ExecResult is client.ExecResult
