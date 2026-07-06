## ADDED Requirements

### Requirement: Per-agent MCP 审批规则配置

每个 agent↔MCP-server 绑定 SHALL 可独立配置一份 `approval_rules`(哪些工具调用需人工审批),存于绑定表 `agent_mcp_servers` 的 `approval_rules` 列(JSON,默认空列表)。同一 MCP server 被不同 agent 绑定时,各绑定的 `approval_rules` SHALL 互相独立、互不影响。审批规则 SHALL NOT 存在 MCP 服务定义(`mcp_servers`)上。

平台 SHALL 提供 `GET /admin/agents/{name}/mcp/{server_id}/approval-rules`(返回该绑定的规则,任意已登录用户可读)与 `PUT /admin/agents/{name}/mcp/{server_id}/approval-rules`(admin 写入;body 携带 `approval_rules` 列表)。PUT 写入前 SHALL 用 `McpApprovalRule` 校验每条规则(缺 `tool`、`when` 非字典等结构错误 SHALL 被拒绝 422),且仅当该 (agent, server) 已绑定时才允许配置(未绑定 SHALL 返回 404)。

materialize 物化某 agent 的 `agent.yaml` 时,每个已绑定 server 的 `x-fleetent.approval_rules` SHALL 取自**该 agent 对该 server 的绑定**记录(而非服务定义);`degrade_mode`/`file_isolation`/`file_root` 仍取自服务定义。规则的 `{ tool, when }` 形状与运行时 `approval_policy` 的读法不变:`when` 为 `null`/缺省=整工具审批,`when` 为 `{参数名: [允许值...]}`=按参数值匹配才审批。

React 管理 SPA 的 agent 详情 MCP 标签页 SHALL 为每个已绑定 server 提供配置其 `approval_rules` 的入口。规则里的**工具名 SHALL 以下拉候选呈现**,候选项取自该 server 的实时工具列表(`GET /admin/mcp/servers/{id}/tools`);当工具列表取不到(服务未连通/probe 失败)或需填列表外的工具名时,SHALL 允许手动输入自定义值。

#### Scenario: 同一 server 不同 agent 各配一套规则

- **WHEN** agent A 与 agent B 都绑定了 server `mailer`,A 配 `approval_rules=[{tool: send_email, when: null}]`、B 不配
- **THEN** A 的 `agent.yaml` 中 `mcpServers.mailer.x-fleetent.approval_rules` 含该规则,B 的 `agent.yaml` 中 `mailer` 无 `approval_rules`

#### Scenario: 工具名从服务工具列表选择

- **WHEN** 管理员在 agent 的 MCP 标签页为已绑定且可连通的 server 配置审批规则
- **THEN** 工具名字段以该 server `GET /admin/mcp/servers/{id}/tools` 返回的工具名作为下拉候选,并允许输入候选外的自定义值

#### Scenario: 未绑定时不可配置

- **WHEN** 对某 agent 未绑定的 server 调 `PUT /admin/agents/{name}/mcp/{server_id}/approval-rules`
- **THEN** 响应为 404,不写入

#### Scenario: 非法规则被拒绝

- **WHEN** PUT body 的 `approval_rules` 中有一条缺 `tool` 字段
- **THEN** 响应为 422,不写入
