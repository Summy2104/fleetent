# agent-definition Delta

## ADDED Requirements

### Requirement: Agent 绑定表声明 agents.id 外键与级联
平台侧引用 agent 的从属/绑定表 SHALL 以 `agent_id`（INTEGER，= `agents.id`）声明 FK→`agents.id` ON DELETE CASCADE，使 agent 删除时其全部绑定/从属行由约束级联清理（不依赖应用层手工清理）。覆盖：`user_agents`、`channel_agents`、`agent_versions`、`mcp_servers`（正名后的 MCP 注册表）、`agent_secrets`（以及阶段 2/3 已处理的 `agent_kbs`、`agent_skills`、`agent_admin_state`、`session_meta`，与已带 FK 的 `agent_mcp_servers` 绑定表、`agent_oauth_bindings`）。例外：`connectors.agent_id` 为休眠列（运行路径未写入），不在本约束内，待真实接入再规整。

#### Scenario: 五表均带 agents.id FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `user_agents` / `channel_agents` / `agent_versions` / `mcp_servers` / `agent_secrets` 各声明 FK→`agents.id` ON DELETE CASCADE

#### Scenario: 删除 agent 级联清理全部绑定
- **WHEN** 一个持有用户分配 / 渠道绑定 / 版本 / MCP server 定义 / MCP 绑定 / secret 的 agent 被删除
- **THEN** 这些表中该 agent 的行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 休眠列不强加 FK
- **WHEN** 审视 `connectors.agent_id`
- **THEN** 它不声明 agents.id FK（休眠列、运行路径未消费），不在本约束范围

### Requirement: MCP server 注册表与绑定表命名对齐既有惯例
MCP 的两张管理表 SHALL 按"注册表 vs 绑定表"正名，与 skills/kbs 绑定家族及 `connectors` 注册表的既有命名惯例一致：MCP server 连接定义（含全局 `agent_id=NULL` 行）的注册表命名为 `mcp_servers`（无 `agent_` 前缀，对齐 `connectors`）；agent↔MCP server 的绑定表命名为 `agent_mcp_servers`（对齐 `agent_skills`/`agent_kbs`）。改名 SHALL 不改变运行时行为：materialize 的 MCP 解析（绑定取 id、注册表取定义）在新表名下结果不变。

#### Scenario: 注册表与绑定表名各就各位
- **WHEN** 管理库迁移运行到最新版本
- **THEN** 存在 `mcp_servers`（MCP server 定义注册表，原 `agent_mcp_servers`）与 `agent_mcp_servers`（agent↔server 绑定表，原 `agent_mcp_server_bindings`）；旧名 `agent_mcp_server_bindings` 不再存在

#### Scenario: 改名后 MCP 解析行为不变
- **WHEN** materialize 为某 agent 解析 MCP servers
- **THEN** 仍从绑定表（`agent_mcp_servers`）+ 版本快照 union 取 server_id，从注册表（`mcp_servers`）取定义（per-agent 行优先、全局 `agent_id=NULL` 行兜底），结果与改名前一致
