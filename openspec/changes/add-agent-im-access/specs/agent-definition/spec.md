# agent-definition Delta

## MODIFIED Requirements

### Requirement: Agent 绑定表声明 agents.id 外键与级联
平台侧引用 agent 的从属/绑定表 SHALL 以 `agent_id`（INTEGER，= `agents.id`）声明 FK→`agents.id` ON DELETE CASCADE，使 agent 删除时其全部绑定/从属行由约束级联清理（不依赖应用层手工清理）。覆盖：`user_agents`、`agent_versions`、`mcp_servers`（正名后的 MCP 注册表）、`agent_secrets`、`agent_mcp_servers`（MCP 绑定表）、`agent_oauth_bindings`（OAuth 绑定表）、`agent_im_groups`（IM 群白名单，IM 访问模型阶段 2 新增），以及阶段 2/3 已处理的 `agent_kbs`、`agent_skills`、`agent_admin_state`、`session_meta`——**全部 agent 引用表无一例外均 CASCADE**。例外：`connectors.agent_id` 为休眠列（运行路径未写入），不在本约束内，待真实接入再规整。

#### Scenario: 各 agent 绑定表均带 agents.id FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `user_agents` / `agent_versions` / `mcp_servers` / `agent_secrets` / `agent_im_groups` 各声明 FK→`agents.id` ON DELETE CASCADE

#### Scenario: 删除 agent 级联清理全部绑定
- **WHEN** 一个持有用户分配 / 版本 / MCP server 定义 / MCP 绑定 / secret / IM 群白名单的 agent 被删除
- **THEN** 这些表中该 agent 的行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 休眠列不强加 FK
- **WHEN** 审视 `connectors.agent_id`
- **THEN** 它不声明 agents.id FK（休眠列、运行路径未消费），不在本约束范围
