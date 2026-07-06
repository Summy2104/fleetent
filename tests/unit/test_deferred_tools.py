"""Unit tests for deferred-tool-loading pure helpers (tools/deferred.py)."""

from fleetent.tools import deferred


def _schema(name: str, description: str = "") -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": {}},
    }


# --- is_hot_tool (Task 2.1) -------------------------------------------------


def test_builtin_tool_always_hot() -> None:
    """A builtin tool name (no `__`) is hot regardless of hot_mcp_servers."""
    assert deferred.is_hot_tool("read_file", []) is True
    assert deferred.is_hot_tool("tool_search", ["crm__*"]) is True


def test_mcp_tool_deferred_when_no_patterns() -> None:
    """An MCP tool (`server__tool`) is not hot when hot_mcp_servers is empty."""
    assert deferred.is_hot_tool("crm__create_lead", []) is False


def test_mcp_tool_hot_when_pattern_matches() -> None:
    """fnmatch against canonical name promotes matching MCP tools to hot."""
    assert deferred.is_hot_tool("crm__create_lead", ["crm__*"]) is True
    assert deferred.is_hot_tool("jira__create_issue", ["jira__create_*"]) is True


def test_mcp_tool_not_hot_when_pattern_mismatch() -> None:
    assert deferred.is_hot_tool("jira__get_issue", ["jira__create_*"]) is False
    assert deferred.is_hot_tool("crm__create_lead", ["slack__*"]) is False


# --- one_line_desc (Task 2.5) -----------------------------------------------


def test_one_line_desc_takes_first_line() -> None:
    s = _schema("t", "First line summary.\nSecond paragraph ignored.")
    assert deferred.one_line_desc(s) == "First line summary."


def test_one_line_desc_strips_newlines_and_truncates() -> None:
    long = "x" * 200
    s = _schema("t", long)
    out = deferred.one_line_desc(s, max_len=80)
    assert "\n" not in out
    assert len(out) <= 80


def test_one_line_desc_empty_description() -> None:
    assert deferred.one_line_desc(_schema("t", "")) == ""


# --- search_deferred (Task 2.3) ---------------------------------------------


def _candidates() -> dict:
    return {
        "crm__create_lead": _schema("crm__create_lead", "Create a new sales lead in the CRM."),
        "crm__list_leads": _schema("crm__list_leads", "List existing sales leads."),
        "slack__post_message": _schema("slack__post_message", "Post a message to a channel."),
        "jira__create_issue": _schema("jira__create_issue", "Create a Jira issue ticket."),
    }


def test_keyword_match_ranks_and_returns_names() -> None:
    hits = deferred.search_deferred("lead", _candidates())
    assert "crm__create_lead" in hits
    assert "crm__list_leads" in hits
    # an unrelated tool is not matched
    assert "slack__post_message" not in hits


def test_keyword_match_name_weighted_above_description() -> None:
    """A query token in the name ranks above one only in another tool's description."""
    cands = {
        "crm__lead_score": _schema("crm__lead_score", "Score an opportunity."),
        "crm__opportunity": _schema("crm__opportunity", "Manage a lead pipeline entry."),
    }
    hits = deferred.search_deferred("lead", cands, limit=2)
    assert hits[0] == "crm__lead_score"


def test_keyword_match_respects_limit() -> None:
    hits = deferred.search_deferred("create", _candidates(), limit=1)
    assert len(hits) == 1


def test_select_exact_returns_only_named() -> None:
    hits = deferred.search_deferred("select:crm__create_lead,jira__create_issue", _candidates())
    assert set(hits) == {"crm__create_lead", "jira__create_issue"}


def test_select_skips_unknown_names() -> None:
    hits = deferred.search_deferred("select:crm__create_lead,does__not_exist", _candidates())
    assert hits == ["crm__create_lead"]


# --- build_deferred_catalog (Task 3.1) --------------------------------------


def test_catalog_lists_name_and_desc_one_line() -> None:
    pool = {
        "crm__create_lead": _schema("crm__create_lead", "Create a new sales lead.\nDetails..."),
    }
    text = deferred.build_deferred_catalog(pool, activated=set())
    assert "crm__create_lead" in text
    assert "Create a new sales lead." in text
    # one entry → one line of content, no embedded description newline
    assert "Details..." not in text


def test_catalog_excludes_activated() -> None:
    pool = {
        "crm__create_lead": _schema("crm__create_lead", "Create a lead."),
        "crm__list_leads": _schema("crm__list_leads", "List leads."),
    }
    text = deferred.build_deferred_catalog(pool, activated={"crm__create_lead"})
    assert "crm__list_leads" in text
    assert "crm__create_lead" not in text


def test_catalog_empty_when_no_deferred() -> None:
    assert deferred.build_deferred_catalog({}, activated=set()) == ""


# --- partition_schemas / assemble_turn_schemas (Task 5.3) -------------------


def test_partition_splits_hot_and_deferred() -> None:
    schemas = [
        _schema("read_file", "Read a file."),
        _schema("tool_search", "Search tools."),
        _schema("crm__create_lead", "Create lead."),
        _schema("crm__list_leads", "List leads."),
    ]
    hot, pool = deferred.partition_schemas(schemas, hot_mcp_servers=[])
    hot_names = {s["function"]["name"] for s in hot}
    assert hot_names == {"read_file", "tool_search"}
    assert set(pool) == {"crm__create_lead", "crm__list_leads"}


def test_partition_promotes_hot_mcp_servers() -> None:
    schemas = [
        _schema("crm__create_lead", "Create lead."),
        _schema("jira__get_issue", "Get issue."),
    ]
    hot, pool = deferred.partition_schemas(schemas, hot_mcp_servers=["crm__*"])
    assert {s["function"]["name"] for s in hot} == {"crm__create_lead"}
    assert set(pool) == {"jira__get_issue"}


def test_partition_uses_canonical_resolver() -> None:
    """When MCP names are projected, the hot decision resolves back to canonical."""
    schemas = [_schema("createLead", "Create lead.")]  # projected (model-facing) name
    resolve = {"createLead": "crm__create_lead"}.get
    hot, pool = deferred.partition_schemas(
        schemas,
        hot_mcp_servers=["crm__*"],
        resolve_canonical=lambda n: resolve(n) or n,
    )
    assert {s["function"]["name"] for s in hot} == {"createLead"}
    assert pool == {}


def test_assemble_turn_schemas_hot_plus_activated() -> None:
    hot = [_schema("read_file"), _schema("tool_search")]
    pool = {
        "crm__create_lead": _schema("crm__create_lead"),
        "crm__list_leads": _schema("crm__list_leads"),
    }
    out = deferred.assemble_turn_schemas(hot, pool, activated={"crm__create_lead"})
    names = [s["function"]["name"] for s in out]
    assert names == ["read_file", "tool_search", "crm__create_lead"]


def test_assemble_ignores_activated_not_in_pool() -> None:
    hot = [_schema("read_file")]
    out = deferred.assemble_turn_schemas(hot, {}, activated={"ghost__tool"})
    assert [s["function"]["name"] for s in out] == ["read_file"]
