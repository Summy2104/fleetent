"""Unit: central approval policy (approval-boundary-redesign).

`approval_policy.risk_for` is the single authority that maps a tool call to a risk
band on the recipient-identity axis: approval ⟺ proactive delivery to a recipient
other than the current conversation participant. Non-outbound tools fall back to their
registered static risk; MCP tools default to no-approval unless a configured rule
matches; broken/unresolvable inputs fail closed to medium.
"""

from __future__ import annotations

import types

import pytest

from fleetent.governance import approval_policy
from fleetent.tools.registry import ToolContext


def _ctx(chat_type="dm", sender_id="U_ME", channel="D_ME"):
    sc = types.SimpleNamespace(
        platform="slack", sender_id=sender_id, chat_type=chat_type, channel_name=channel
    )
    return ToolContext(session_context=sc)


@pytest.fixture(autouse=True)
def _clear_rules():
    approval_policy.reset_mcp_rules()
    yield
    approval_policy.reset_mcp_rules()


# --- Task 1: core entry, fallback passthrough, anti-escape, fail-closed ---


def test_non_outbound_returns_fallback_medium():
    # run_code-like: not an outbound-to-others tool → policy returns its static fallback
    assert approval_policy.risk_for("run_code", {}, _ctx(), fallback="medium") == "medium"


def test_unknown_tool_returns_fallback_none():
    assert approval_policy.risk_for("read_file", {}, _ctx(), fallback="none") == "none"


def test_anti_escape_ignores_args_risk_field():
    # the LLM cannot lower a tool below its band by stuffing risk into args
    out = approval_policy.risk_for(
        "run_code", {"risk": "none", "risk_level": "none"}, _ctx(), fallback="medium"
    )
    assert out == "medium"


def test_fallback_defaults_to_none_when_omitted():
    assert approval_policy.risk_for("read_file", {}, _ctx()) == "none"


# --- Task 1.3: registry.evaluate_risk_level delegates to the policy ---


def test_registry_evaluate_delegates_to_policy(monkeypatch):
    from unittest.mock import MagicMock

    from fleetent.tools import registry

    # register a tool with a static medium band so we can assert it flows as `fallback`
    @registry.tool(risk_level="medium")
    def _probe_tool():  # pragma: no cover - never executed
        return ""

    spy = MagicMock(return_value="low")
    monkeypatch.setattr(approval_policy, "risk_for", spy)
    ctx = _ctx()
    out = registry.evaluate_risk_level("_probe_tool", {"x": 1}, ctx)

    assert out == "low"  # policy's verdict propagates
    spy.assert_called_once()
    call_kwargs = spy.call_args.kwargs
    assert call_kwargs.get("fallback") == "medium"  # the registered static band flows through


# --- Task 2: send_im_message recipient-identity axis ---


def test_send_im_to_current_dm_user_is_none():
    ctx = _ctx(chat_type="dm", sender_id="U_ME", channel="D_ME")
    args = {"target": "U_ME", "target_type": "user"}
    assert approval_policy.risk_for("send_im_message", args, ctx, fallback="medium") == "none"


def test_send_im_to_other_user_is_medium():
    ctx = _ctx(chat_type="dm", sender_id="U_ME", channel="D_ME")
    args = {"target": "U_OTHER", "target_type": "user"}
    assert approval_policy.risk_for("send_im_message", args, ctx, fallback="none") == "medium"


def test_send_im_to_current_channel_is_none():
    ctx = _ctx(chat_type="channel", sender_id="U_ME", channel="C_HERE")
    args = {"target": "C_HERE", "target_type": "channel"}
    assert approval_policy.risk_for("send_im_message", args, ctx, fallback="medium") == "none"


def test_send_im_to_other_channel_is_medium():
    ctx = _ctx(chat_type="channel", sender_id="U_ME", channel="C_HERE")
    args = {"target": "C_OTHER", "target_type": "channel"}
    assert approval_policy.risk_for("send_im_message", args, ctx, fallback="none") == "medium"


def test_send_im_default_target_type_is_user():
    ctx = _ctx(chat_type="dm", sender_id="U_ME", channel="D_ME")
    # target_type omitted defaults to "user"
    assert approval_policy.risk_for("send_im_message", {"target": "U_ME"}, ctx) == "none"


def test_send_im_no_session_context_fails_closed_medium():
    ctx = ToolContext(session_context=None)
    args = {"target": "U_ME", "target_type": "user"}
    assert approval_policy.risk_for("send_im_message", args, ctx, fallback="none") == "medium"


# --- Task 3: send_file is always no-approval ---


def test_send_file_always_none_even_with_medium_fallback():
    out = approval_policy.risk_for(
        "send_file", {"path": "/exchange/srv/a.txt"}, _ctx(), fallback="medium"
    )
    assert out == "none"


def test_send_file_not_dynamic_risk_in_registry():
    import fleetent.tools.builtin_tools  # noqa: F401 — ensure registration side effects
    from fleetent.tools import registry

    assert registry.is_dynamic_risk("send_file") is False
    assert registry.get_risk_level("send_file") == "none"


# --- Task 4: invoke_agent no-approval ---


def test_invoke_agent_is_none_even_with_medium_fallback():
    out = approval_policy.risk_for(
        "invoke_agent", {"agent_name": "x", "message": "y"}, _ctx(), fallback="medium"
    )
    assert out == "none"


def test_invoke_agent_registry_static_none():
    import fleetent.tools.builtin_tools  # noqa: F401 — registration side effect
    from fleetent.tools import registry

    assert registry.get_risk_level("invoke_agent") == "none"


# --- Task 5.1: agent.yaml mcp_servers[].approval_rules parsing ---


def test_mcp_server_settings_parses_approval_rules():
    from fleetent.config import McpServerSettings

    s = McpServerSettings.model_validate(
        {
            "id": "google-workspace",
            "approval_rules": [
                {"tool": "manage_email", "when": {"operation": ["send", "reply"]}},
                {"tool": "danger_tool"},
            ],
        }
    )
    assert s.approval_rules[0].tool == "manage_email"
    assert s.approval_rules[0].when == {"operation": ["send", "reply"]}
    assert s.approval_rules[1].tool == "danger_tool"
    assert s.approval_rules[1].when is None


def test_mcp_server_settings_approval_rules_default_empty():
    from fleetent.config import McpServerSettings

    assert McpServerSettings.model_validate({"id": "x"}).approval_rules == []


# --- Task 5.3: MCP rule matching in risk_for ---


def test_mcp_unconfigured_server_is_none():
    # no rules installed → MCP tool defaults to no-approval
    assert approval_policy.risk_for("srv__do_thing", {}, _ctx()) == "none"


def test_mcp_rule_matches_by_arg():
    approval_policy.set_agent_mcp_rules(
        {"srv": [{"tool": "manage_email", "when": {"operation": ["send", "reply"]}}]}
    )
    assert approval_policy.risk_for("srv__manage_email", {"operation": "send"}, _ctx()) == "medium"


def test_mcp_rule_arg_miss_is_none():
    approval_policy.set_agent_mcp_rules(
        {"srv": [{"tool": "manage_email", "when": {"operation": ["send"]}}]}
    )
    assert approval_policy.risk_for("srv__manage_email", {"operation": "search"}, _ctx()) == "none"


def test_mcp_whole_tool_rule_no_when():
    approval_policy.set_agent_mcp_rules({"srv": [{"tool": "danger"}]})
    assert approval_policy.risk_for("srv__danger", {"anything": 1}, _ctx()) == "medium"


def test_mcp_multi_arg_when_is_and():
    approval_policy.set_agent_mcp_rules({"srv": [{"tool": "t", "when": {"a": ["1"], "b": ["2"]}}]})
    # both must match
    assert approval_policy.risk_for("srv__t", {"a": "1", "b": "2"}, _ctx()) == "medium"
    assert approval_policy.risk_for("srv__t", {"a": "1", "b": "9"}, _ctx()) == "none"


# --- Task 6: built-in google-workspace email default rule ---


def test_builtin_google_workspace_email_send_gated():
    # no configured rules for the server → built-in default gates manage_email send
    out = approval_policy.risk_for("google-workspace__manage_email", {"operation": "send"}, _ctx())
    assert out == "medium"


def test_builtin_google_workspace_email_read_no_approval():
    out = approval_policy.risk_for(
        "google-workspace__manage_email", {"operation": "search"}, _ctx()
    )
    assert out == "none"


def test_explicit_config_overrides_builtin_default():
    approval_policy.set_agent_mcp_rules(
        {"google-workspace": [{"tool": "manage_drive", "when": {"operation": ["delete"]}}]}
    )
    # built-in email rule no longer applies (server now explicitly configured)
    assert (
        approval_policy.risk_for("google-workspace__manage_email", {"operation": "send"}, _ctx())
        == "none"
    )
    assert (
        approval_policy.risk_for("google-workspace__manage_drive", {"operation": "delete"}, _ctx())
        == "medium"
    )
