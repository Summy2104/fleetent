"""Unit: AgentFile 读取标准 mcpServers map 外形 + tool_naming + ${VAR} 引用不被误判。

覆盖 mcp-config-standardization 的 agent.yaml 解析层(AgentFile):
- 接受 mcpServers / mcp_servers map(key = server id),x-fleetent 扩展生效
- mcp.tool_naming 默认 claude,支持自定义 template
- legacy list-of-id 被拒
- AgentFile 路径保留 ${VAR} 引用(不 eager 展开),且不被 _reject_inline_secrets 误判
"""

from __future__ import annotations

import pytest

from fleetent import agent_config
from fleetent.config import McpToolNamingTemplate


def _doc(**fields):
    doc = {"name": "a", "version": 1, "models": agent_config.default_models().model_dump()}
    doc.update(fields)
    return doc


def test_agentfile_accepts_mcpservers_map() -> None:
    af = agent_config.AgentFile.model_validate(
        _doc(
            mcpServers={
                "github": {"command": "npx", "args": ["-y", "srv"]},
                "crm": {
                    "url": "https://crm.internal/mcp",
                    "x-fleetent": {
                        "degrade_mode": "strict",
                        "approval_rules": [{"tool": "create_contact"}],
                    },
                },
            }
        )
    )
    servers = {s.id: s for s in af.mcp_servers}
    assert set(servers) == {"github", "crm"}
    assert servers["github"].transport == "stdio"
    assert servers["crm"].transport == "http"
    assert servers["crm"].degrade_mode == "strict"
    assert [r.tool for r in servers["crm"].approval_rules] == ["create_contact"]


def test_agentfile_default_tool_naming_is_claude() -> None:
    af = agent_config.AgentFile.model_validate(_doc())
    assert af.mcp.tool_naming == "claude"


def test_agentfile_custom_tool_naming_template() -> None:
    af = agent_config.AgentFile.model_validate(
        _doc(mcp={"enabled": True, "tool_naming": {"template": "{server}:{tool}"}})
    )
    assert isinstance(af.mcp.tool_naming, McpToolNamingTemplate)
    assert af.mcp.tool_naming.template == "{server}:{tool}"


def test_legacy_list_form_rejected_on_file_load(tmp_path) -> None:
    import yaml

    path = tmp_path / "agent.yaml"
    path.write_text(
        yaml.safe_dump(_doc(mcp_servers=[{"id": "github", "command": "npx"}])),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="legacy list"):
        agent_config.load_agent_home_file(path)


def test_var_ref_header_kept_and_not_flagged(tmp_path) -> None:
    af = agent_config.AgentFile.model_validate(
        _doc(
            mcpServers={
                "crm": {
                    "url": "https://crm.internal/mcp",
                    "headers": {"Authorization": "Bearer ${CRM_TOKEN}"},
                }
            }
        )
    )
    # AgentFile path keeps the ${VAR} reference (no eager expansion).
    assert af.mcp_servers[0].headers["Authorization"] == "Bearer ${CRM_TOKEN}"
    # A ${VAR} reference must NOT be rejected as an inline secret.
    agent_config._reject_inline_secrets(af, tmp_path / "agent.yaml")
