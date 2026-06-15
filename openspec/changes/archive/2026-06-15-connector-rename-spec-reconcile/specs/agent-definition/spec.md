# agent-definition Specification

## MODIFIED Requirements

### Requirement: Agent hard deletion

The store SHALL expose `agent_store.delete_agent(name)` that removes the agent and all its dependent rows in a single transaction. Every agent-referencing table carries FK→agents.id ON DELETE CASCADE (identity-model 阶段 2–4，含 binding 表 `agent_mcp_servers` / `agent_service_grants`)，so the store resolves the agent id by name and issues a single `DELETE FROM agents`; the cascade removes all versions / bindings / satellites with no orphans and no manual child deletes. It SHALL return a boolean: `True` when a row was deleted, `False` when no agent with that name exists. SQL SHALL use named parameters and go through the store boundary; no ORM.

#### Scenario: Delete removes agents and agent_versions rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an existing agent with N versions
- **THEN** the `agents` row and all N `agent_versions` rows are removed in one transaction AND the call returns `True`

#### Scenario: Delete cleans binding child rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an agent holding MCP server bindings and external-service grants
- **THEN** the `agent_mcp_servers` and `agent_service_grants` rows for that agent are removed in the same transaction（FK 强制下不报约束错误，且不留孤儿绑定行）

#### Scenario: Delete of unknown agent returns False

- **WHEN** `agent_store.delete_agent("nope")` is called and no such agent exists
- **THEN** no rows are modified AND the call returns `False`

### Requirement: Agent 绑定表声明 agents.id 外键与级联
平台侧引用 agent 的从属/绑定表 SHALL 以 `agent_id`（INTEGER，= `agents.id`）声明 FK→`agents.id` ON DELETE CASCADE，使 agent 删除时其全部绑定/从属行由约束级联清理（不依赖应用层手工清理）。覆盖：`user_agents`、`agent_versions`、`mcp_servers`（正名后的 MCP 注册表）、`agent_secrets`、`agent_mcp_servers`（MCP 绑定表）、`agent_service_grants`（外部服务授权表，正名自 `agent_oauth_bindings`）、`agent_im_groups`（IM 群白名单，IM 访问模型阶段 2 新增），以及阶段 2/3 已处理的 `agent_kbs`、`agent_skills`、`agent_admin_state`、`session_meta`——**全部 agent 引用表无一例外均 CASCADE**。注：原 `connectors.agent_id` 休眠列已随 `connectors`→`external_services` 重塑移除（服务注册表为单层全局，无 owning-agent 维度），不再存在该例外。

#### Scenario: 各 agent 绑定表均带 agents.id FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `user_agents` / `agent_versions` / `mcp_servers` / `agent_secrets` / `agent_mcp_servers` / `agent_service_grants` / `agent_im_groups` 各声明 FK→`agents.id` ON DELETE CASCADE

#### Scenario: 删除 agent 级联清理全部绑定
- **WHEN** 一个持有用户分配 / 版本 / MCP server 定义 / MCP 绑定 / 外部服务授权 / secret / IM 群白名单的 agent 被删除
- **THEN** 这些表中该 agent 的行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 服务注册表无 owning-agent 维度
- **WHEN** 审视 `external_services`
- **THEN** 它为单层全局注册表、无 `agent_id` 列、不参与 per-agent FK 约束（per-principal 差异由 `external_credentials` 承载）
