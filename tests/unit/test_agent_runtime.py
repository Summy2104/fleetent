"""Unit tests for agent_runtime pure helpers (no DB required)."""

from fleetent.runtime.snapshot import filter_tool_schemas


def _schema(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": "", "parameters": {}}}


def _names(schemas: list[dict]) -> set[str]:
    return {s["function"]["name"] for s in schemas}


SCHEMAS = [
    _schema("shell"),
    _schema("web_search"),
    _schema("github__create_issue"),
    _schema("github__list_prs"),
    _schema("gitlab__create_issue"),
]


def test_allowed_tools_none_keeps_all_when_mcp_none():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=None, mcp_server_ids=None)
    assert _names(out) == _names(SCHEMAS)


def test_allowed_tools_fnmatch_filters():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=["shell", "github__*"], mcp_server_ids=None)
    assert _names(out) == {"shell", "github__create_issue", "github__list_prs"}


def test_mcp_allowlist_keeps_only_listed_server():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=None, mcp_server_ids=["github"])
    assert _names(out) == {"shell", "web_search", "github__create_issue", "github__list_prs"}


def test_mcp_empty_list_excludes_all_mcp_tools():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=None, mcp_server_ids=[])
    assert _names(out) == {"shell", "web_search"}


def test_mcp_none_means_no_mcp_filter():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=None, mcp_server_ids=None)
    assert "gitlab__create_issue" in _names(out)


def test_double_filter_both_applied():
    # allowed_tools admits github__* and gitlab__*, but mcp allowlist only github
    out = filter_tool_schemas(
        SCHEMAS, allowed_tools=["github__*", "gitlab__*"], mcp_server_ids=["github"]
    )
    assert _names(out) == {"github__create_issue", "github__list_prs"}


def test_allowed_wildcard_but_server_not_whitelisted_hides_all():
    out = filter_tool_schemas(SCHEMAS, allowed_tools=["github__*"], mcp_server_ids=[])
    assert _names(out) == set()
