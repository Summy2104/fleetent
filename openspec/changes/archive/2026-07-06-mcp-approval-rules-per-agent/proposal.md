## Why

上一个 change（`mcp-admin-xfleetent-fields`）把 `approval_rules` 放在 **MCP 服务定义级**（`mcp_servers` 表 + MCP 服务表单）。但审批规则天然是 **per-agent 策略**:同一个 MCP 服务被不同 agent 绑定,各自允许的工具、各自要审批的操作都不同,放在服务级会让所有绑定该服务的 agent 共用同一套规则,不符合真实需求。

同时,审批规则里的工具名当前是**手填文本框**,容易拼错、也不知道该服务到底暴露了哪些工具。该服务的真实工具列表已可经 `GET /admin/mcp/servers/{id}/tools`(实时 probe)取得,应据此改成下拉选择。

## What Changes

- **存储位置迁移**:`approval_rules` 从 `mcp_servers`(服务定义)搬到 `agent_mcp_servers`(每个 agent↔server 绑定)。同一服务被不同 agent 绑定可各配一套。`agent.yaml` 的 `mcpServers.<id>.x-fleetent.approval_rules` 形状与运行时读法(`governance/approval_policy`)**完全不变**——变的只是平台侧「在哪配、存哪」。
- **数据模型**:`agent_mcp_servers` 加 `approval_rules`(JSON,默认 `[]`)列(沿用该表既有的 `enabled`/`headers` 每绑定配置老路);`mcp_servers` 删 `approval_rules` 列。一支 Alembic 迁移完成加列 + 删列(上一个 change 刚上线、无正式数据,直接删,不迁移旧数据)。
- **后端**:
  - 绑定 store(`agent_store`)加读/写某 (agent, server) 的 `approval_rules`。
  - agent 侧 API(`agent_admin_api`)加 `GET/PUT /admin/agents/{name}/mcp/{server_id}/approval-rules`,写入前用 `config.McpApprovalRule` 校验(校验逻辑从 connector 侧挪来)。
  - `materialize._mcp_servers_for_agent` 改成从**绑定**读 `approval_rules` 塞进 `McpServerSettings`;`degrade_mode`/`file_root`/`file_isolation` 仍从服务定义读。
  - `connector_admin_api` 的 create/edit body、`GET /admin/mcp/servers` 响应、`mcp_server_store` **移除** `approval_rules`(其余 3 个 x-fleetent 字段保留)。
- **前端**:
  - MCP 服务表单(`server-dialog`)去掉审批规则编辑器(保留降级策略/文件隔离/文件根目录)。
  - agent 的 MCP 绑定标签页(`mcp-servers-tab`)每个已绑定 server 加「配置审批规则」入口;`ApprovalRulesEditor` 从服务对话框搬到 agent 标签页复用。
  - 工具名字段从手填文本框改成**可输入下拉(combobox)**:选项取自该 server 的工具列表(`GET /admin/mcp/servers/{id}/tools`),取不到/想填自定义时仍允许手填。

## Capabilities

### New Capabilities

(无)

### Modified Capabilities

- `agent-mcp-binding`:新增「per-agent MCP 审批规则」——每个 agent↔server 绑定可独立配置 `approval_rules`,工具名从该服务实时工具列表选择,物化进该 agent 的 `agent.yaml`。
- `mcp-server-admin`:MCP 服务表单的 x-fleetent 编辑范围**收窄**——`approval_rules` 移除(改由 agent 绑定处配置),仅保留 `degrade_mode`/`file_isolation`/`file_root`。

## Impact

- **owning package**:`platform/agent_management_console`(agent_admin_api)、`agent_store`(绑定表读写)、`platform/connector_management`(移除服务级 approval_rules)、`platform/agent_lifecycle`(materialize 改读绑定)、`frontend/src/features/agents`(+ `features/mcp` 移除)。`config.py` 的 `McpApprovalRule`/`McpServerSettings.approval_rules` 不变。
- **public API surface**:**新增** `GET/PUT /admin/agents/{name}/mcp/{server_id}/approval-rules`;**移除** `POST/PUT/GET /admin/mcp/servers` 的 `approval_rules` 字段。`GET /admin/mcp/servers/{id}/tools` 复用,不改。
- **owned tables**:管理库 `agent_mcp_servers` 加 `approval_rules` 列、`mcp_servers` 删 `approval_rules` 列(Alembic 119,down_revision 118)。
- **config namespace**:`mcpServers.<id>.x-fleetent.approval_rules` 不变(仅平台存储位置从服务表迁到绑定表)。
- **cross-module dependencies**:`agent_admin_api` import `config.McpApprovalRule` 做校验(中立核心);`materialize` 读 `agent_store` 绑定的 approval_rules。无新增反向依赖。
- **migration / shim plan**:Alembic 119 加 `agent_mcp_servers.approval_rules`(server_default `'[]'`)+ 删 `mcp_servers.approval_rules`;downgrade 反向。不迁移旧数据(上一个 change 无正式数据)。
- **边界**:不改 `agent.yaml` 的 x-fleetent 形状、不改 `approval_policy` 匹配逻辑、不改工具 probe 端点。
