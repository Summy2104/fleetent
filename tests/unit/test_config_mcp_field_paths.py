"""Unit: mcp_yaml_field_paths() derives McpServerSettings field -> agent.yaml path
templates from the same MCP_FLEETENT_EXT_DEFAULTS hoisting rule materialize's
_mcp_payload_to_map uses, so the two can never drift apart."""

from __future__ import annotations

from fleetent.config import mcp_yaml_field_paths


def test_top_level_fields_are_not_hoisted_under_x_fleetent() -> None:
    paths = mcp_yaml_field_paths()
    assert paths["transport"] == "mcpServers.{id}.transport"
    assert paths["command"] == "mcpServers.{id}.command"
    assert paths["url"] == "mcpServers.{id}.url"
    assert paths["args"] == "mcpServers.{id}.args"
    assert paths["env"] == "mcpServers.{id}.env"
    assert paths["headers"] == "mcpServers.{id}.headers"
    assert paths["auth_type"] == "mcpServers.{id}.auth_type"
    assert paths["api_key_env"] == "mcpServers.{id}.api_key_env"
    assert paths["header_style"] == "mcpServers.{id}.header_style"
    assert paths["credential_input"] == "mcpServers.{id}.credential_input"


def test_oauth_auth_subfields_are_hoisted_under_x_fleetent_auth() -> None:
    paths = mcp_yaml_field_paths()
    for sub in (
        "token_url",
        "client_id",
        "client_secret_env",
        "scope",
        "authorization_endpoint",
        "redirect_path",
        "token_env",
    ):
        assert paths[f"auth.{sub}"] == f"mcpServers.{{id}}.x-fleetent.auth.{sub}"


def test_excludes_map_key_and_unused_timeout_fields() -> None:
    paths = mcp_yaml_field_paths()
    assert "id" not in paths
    assert "connect_timeout" not in paths
    assert "call_timeout" not in paths
    assert "auth" not in paths
