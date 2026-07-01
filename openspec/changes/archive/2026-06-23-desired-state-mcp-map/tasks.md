## 1. desired-state 载荷以 mcpServers map 下发

- [x] 1.1 写测试（unit）：对绑定了 MCP server 的 `AgentFile`，`desired_state_payload_from_agent_file` 输出含 `mcpServers` map（key=server id）、不含 legacy `mcp_servers` list；先见红
- [x] 1.2 写测试（unit）：该 payload 写成 `agent.yaml`（yaml dump）后，`agent_config.load_agent_file` 能成功加载、不抛 `legacy list-of-id` ValueError；先见红
- [x] 1.3 实现：`desired_state_payload_from_agent_file` 在 `_strip_secret_plumbing(model_dump(...))` 之后调用 `_mcp_payload_to_map(payload)` 再返回；令 1.1–1.2 见绿
- [x] 1.4 更新现有断言 list 形态的测试 `tests/unit/platform/node_management/test_node_config_payload.py`：改断言 `mcpServers` map 形态，保留「非密指针保留 / 密钥值剥离」校验；确认仍绿

## 2. change 收尾

- [x] 2.1 `make test-pr` 全绿（3565 passed）
- [x] 2.2 `uv run pytest tests/integration -q` 对照 main 无新增失败（3 个预先存在失败 kb_migrations / proposal routing_key 已在干净 dev-pjh 基底复现，与本改动无关）
