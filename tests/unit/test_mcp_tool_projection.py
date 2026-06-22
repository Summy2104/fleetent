"""Unit: MCP 工具名投影边界(canonical registry + 反查表 + project/resolve + schema 投影)。"""

from __future__ import annotations

import pytest

from fleetent.integrations.mcp import client


@pytest.fixture(autouse=True)
def _clean_projection():
    client._mcp_tool_meta.clear()
    client._forward.clear()
    client._reverse.clear()
    client.set_tool_naming("claude")
    yield
    client._mcp_tool_meta.clear()
    client._forward.clear()
    client._reverse.clear()
    client.set_tool_naming("claude")


def _seed(*items: tuple[str, str, str]) -> None:
    for canonical, server, raw in items:
        client._record_tool_identity(canonical, server, raw)


def test_default_claude_projection() -> None:
    _seed(("github__create_issue", "github", "create_issue"))
    assert client.project_tool_name("github__create_issue") == "mcp__github__create_issue"
    assert client.resolve_tool_name("mcp__github__create_issue") == "github__create_issue"


def test_hermes_projection_and_ambiguous_resolution() -> None:
    client.set_tool_naming("hermes")
    _seed(("google_drive__list_files", "google_drive", "list_files"))
    assert client.project_tool_name("google_drive__list_files") == "mcp_google_drive_list_files"
    # ambiguous single-underscore resolves via the reverse table, NOT by string splitting
    assert client.resolve_tool_name("mcp_google_drive_list_files") == "google_drive__list_files"


def test_non_mcp_names_passthrough() -> None:
    assert client.project_tool_name("calculate") == "calculate"
    assert client.resolve_tool_name("calculate") == "calculate"


def test_mcp_tool_identity() -> None:
    _seed(("crm__create_contact", "crm", "create_contact"))
    assert client.mcp_tool_identity("crm__create_contact") == ("crm", "create_contact")
    assert client.mcp_tool_identity("nope") is None


def test_project_schemas_renames_only_mcp_and_copies() -> None:
    _seed(("github__create_issue", "github", "create_issue"))
    schemas = [
        {"function": {"name": "github__create_issue", "description": "x"}},
        {"function": {"name": "calculate", "description": "y"}},
    ]
    out = client.project_schemas(schemas)
    assert [s["function"]["name"] for s in out] == ["mcp__github__create_issue", "calculate"]
    # the registry's original schema dict must not be mutated
    assert schemas[0]["function"]["name"] == "github__create_issue"


def test_set_tool_naming_rebuilds_maps() -> None:
    _seed(("github__create_issue", "github", "create_issue"))
    client.set_tool_naming("bare")
    assert client.project_tool_name("github__create_issue") == "github__create_issue"
    client.set_tool_naming("hermes")
    assert client.project_tool_name("github__create_issue") == "mcp_github_create_issue"


def test_forget_tool_identity() -> None:
    _seed(("github__create_issue", "github", "create_issue"))
    client._forget_tool_identity("github__create_issue")
    assert client.mcp_tool_identity("github__create_issue") is None
    assert client.project_tool_name("github__create_issue") == "github__create_issue"
