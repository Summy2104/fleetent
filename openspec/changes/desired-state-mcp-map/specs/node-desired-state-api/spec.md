## ADDED Requirements

### Requirement: MCP 配置以标准 mcpServers map 下发

`GET /nodes/{id}/desired-state` 返回的每个 agent 配置载荷中，MCP server 配置 SHALL 以标准 `mcpServers` map 形态（key = server id）下发，MUST NOT 使用 legacy 的 `mcp_servers` list 形态。这与 node 直接 materialize agent home（`write_home` 写 `agent.yaml`）时的形态一致。

agent 运行时 `agent_config.load_agent_file` 已拒绝 legacy `mcp_servers` list（抛 `ValueError: legacy list-of-id 'mcp_servers' is not supported`）；故 desired-state 载荷以 list 形态下发会使任何绑定了 MCP server 的 managed agent 启动即崩溃。本 requirement 保证 node 据载荷写出的 `agent.yaml` 能被运行时成功加载。

map 形态 SHALL 在剥离密钥值之后渲染：先剥离 `env` 字典与 `*credential_ref`（承载密钥值的字段），再把 `mcp_servers` list 改写为 `mcpServers` map；载荷 MUST NOT 含任何明文密钥值。无 MCP server 的 agent 载荷不含 `mcpServers`，且不受影响。

#### Scenario: 绑定 MCP 的 agent 载荷为 mcpServers map

- **WHEN** 某 agent 绑定了 MCP server，node 拉取期望态返回该 agent
- **THEN** 其配置载荷含 `mcpServers` map（key 为 server id），不含 legacy `mcp_servers` list

#### Scenario: 下发载荷可被运行时加载

- **WHEN** node 据 desired-state 载荷写出 `agent.yaml`，agent 进程启动调用 `load_agent_file` 加载
- **THEN** 加载成功，MUST NOT 抛 `legacy list-of-id 'mcp_servers' is not supported` 错误

#### Scenario: map 形态仍剥离密钥值

- **WHEN** 绑定的 MCP server 含承载密钥值的 `env` 字典或 `credential_ref`
- **THEN** 下发载荷的 `mcpServers` 条目中这些密钥值被剥除，不含任何明文密钥
