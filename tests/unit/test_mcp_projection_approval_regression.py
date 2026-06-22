"""Unit(安全防回归核心):任何 tool_naming 下,审批仍绑 canonical (server, raw_tool)。

投影只在 LLM 边界翻译;loop 入站把投影名还原成 canonical 后才做风险判定,因此
approval_policy 永远拿到 canonical `{server}__{tool}`,approval_rules 命中与否与
tool_naming 无关。这条用例锁死「投影不绕过审批」。
"""

from __future__ import annotations

import pytest

from fleetent.governance import approval_policy
from fleetent.integrations.mcp import client


@pytest.fixture(autouse=True)
def _clean():
    approval_policy.reset_mcp_rules()
    client._mcp_tool_meta.clear()
    client._forward.clear()
    client._reverse.clear()
    client.set_tool_naming("claude")
    yield
    approval_policy.reset_mcp_rules()
    client._mcp_tool_meta.clear()
    client._forward.clear()
    client._reverse.clear()
    client.set_tool_naming("claude")


@pytest.mark.parametrize("naming", ["claude", "hermes", "opencode", "skills", "bare"])
def test_approval_rule_matches_under_any_naming(naming: str) -> None:
    approval_policy.set_server_mcp_rules("crm", [{"tool": "create_contact"}])
    client.set_tool_naming(naming)
    client._record_tool_identity("crm__create_contact", "crm", "create_contact")

    # The model calls the projected name; the loop resolves it back to canonical first.
    projected = client.project_tool_name("crm__create_contact")
    canonical = client.resolve_tool_name(projected)
    assert canonical == "crm__create_contact"

    risk = approval_policy.risk_for(canonical, {}, None, fallback="none")
    assert risk == "medium"


@pytest.mark.parametrize("naming", ["claude", "hermes", "bare"])
def test_readonly_tool_not_gated_under_any_naming(naming: str) -> None:
    approval_policy.set_server_mcp_rules("crm", [{"tool": "create_contact"}])
    client.set_tool_naming(naming)
    client._record_tool_identity("crm__get_contact", "crm", "get_contact")

    canonical = client.resolve_tool_name(client.project_tool_name("crm__get_contact"))
    assert approval_policy.risk_for(canonical, {}, None, fallback="none") == "none"
