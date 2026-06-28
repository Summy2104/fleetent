"""Integration guardrails for retiring the tool OAuth vault routes."""

from __future__ import annotations

from pathlib import Path

from fleetent.server import app


def test_tool_oauth_vault_routes_are_not_registered_but_mcp_routes_remain() -> None:
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/admin/connectors" not in paths
    assert "/admin/connectors/grants" not in paths
    assert "/admin/connectors/offboarding/{user_id}" not in paths
    assert "/admin/connectors/authorize/{service_id}" not in paths
    assert "/admin/connectors/callback/{service_id}" not in paths
    assert "/admin/connectors/{service_id}/credentials" not in paths
    assert "/admin/agents/{name}/bindings/oauth" not in paths
    assert "/admin/agents/{name}/bindings/oauth/{connector_id}" not in paths

    assert "/admin/mcp/servers" in paths
    assert "/admin/mcp/servers/{server_id}/tools" in paths


def test_server_source_no_longer_injects_legacy_provider_or_delete_hook() -> None:
    source = Path("src/fleetent/server.py").read_text(encoding="utf-8")

    assert "vault" + "_provider" not in source
    assert "set_provider(" not in source
    assert "set_delete_agent_hook(" not in source
    assert "external" + "_credential_store" not in source
