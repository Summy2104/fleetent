from __future__ import annotations

from fleetent import connectors
from fleetent.tools import builtin_tools  # noqa: F401  # load-bearing registration
from fleetent.tools import registry as tool_registry


def test_builtin_connector_tool_registers_connector_metadata_without_schema_leak():
    schema = next(
        s
        for s in tool_registry.get_schemas()
        if s["function"]["name"] == "github_connection_status"
    )

    assert tool_registry.get_connector("github_connection_status") == ("github", ["repo"])
    assert "client" not in schema["function"]["parameters"]["properties"]
    assert "connector" not in schema["function"]["parameters"]["properties"]


def test_builtin_connector_tool_degrades_to_consent_without_provider_injection():
    result = tool_registry.dispatch("github_connection_status", "{}", user_id="u1")

    assert isinstance(result, str)
    assert "requires authorization" in result
    assert "github" in result
    assert isinstance(connectors.get_credential("u1", "github", ["repo"]), connectors.NeedsConsent)
