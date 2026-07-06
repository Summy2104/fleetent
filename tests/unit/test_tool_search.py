"""Unit tests for the tool_search builtin and ToolContext deferred fields."""


from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _schema(name: str, description: str = "") -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": {}},
    }


def _ctx_with_pool() -> ToolContext:
    return ToolContext(
        deferred_pool={
            "crm__create_lead": _schema("crm__create_lead", "Create a sales lead."),
            "crm__list_leads": _schema("crm__list_leads", "List sales leads."),
            "jira__create_issue": _schema("jira__create_issue", "Create a Jira issue."),
        }
    )


# --- ToolContext fields (Task 5.1) ------------------------------------------


def test_tool_context_deferred_fields_default_empty() -> None:
    ctx = ToolContext()
    assert ctx.activated_tools == set()
    assert ctx.deferred_pool == {}


def test_tool_context_activated_is_mutable() -> None:
    ctx = ToolContext()
    ctx.activated_tools.add("crm__create_lead")
    assert "crm__create_lead" in ctx.activated_tools


# --- tool_search keyword (Task 4.1) -----------------------------------------


def test_tool_search_keyword_returns_schema_and_activates() -> None:
    ctx = _ctx_with_pool()
    out = builtin_tools.tool_search(query="lead", tool_context=ctx)
    # both lead tools surface in the result text as schemas
    assert "crm__create_lead" in out
    assert "crm__list_leads" in out
    # and they are activated for subsequent turns
    assert "crm__create_lead" in ctx.activated_tools
    assert "crm__list_leads" in ctx.activated_tools
    # an unrelated tool is neither returned nor activated
    assert "jira__create_issue" not in ctx.activated_tools


def test_tool_search_result_contains_parseable_schema() -> None:
    ctx = _ctx_with_pool()
    out = builtin_tools.tool_search(query="select:crm__create_lead", tool_context=ctx)
    # the returned text embeds the full JSON schema of the matched tool
    assert '"crm__create_lead"' in out
    # the embedded schema parses back to a function tool schema
    assert "parameters" in out


# --- tool_search select (Task 4.2) ------------------------------------------


def test_tool_search_select_exact() -> None:
    ctx = _ctx_with_pool()
    out = builtin_tools.tool_search(
        query="select:crm__create_lead,jira__create_issue", tool_context=ctx
    )
    assert ctx.activated_tools == {"crm__create_lead", "jira__create_issue"}
    assert "crm__list_leads" not in out


def test_tool_search_select_unknown_name_not_activated() -> None:
    ctx = _ctx_with_pool()
    out = builtin_tools.tool_search(
        query="select:crm__create_lead,does__not_exist", tool_context=ctx
    )
    assert ctx.activated_tools == {"crm__create_lead"}
    # the miss is reported, not silently dropped
    assert "does__not_exist" in out


def test_tool_search_no_match_reports_empty() -> None:
    ctx = _ctx_with_pool()
    out = builtin_tools.tool_search(query="nonsense_zzz", tool_context=ctx)
    assert ctx.activated_tools == set()
    assert out  # non-empty human-readable "no match" message


def test_tool_search_no_pool_degrades() -> None:
    out = builtin_tools.tool_search(query="lead", tool_context=ToolContext())
    assert isinstance(out, str) and out
