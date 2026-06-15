# agent-oauth-binding Specification

## Purpose
Define how agents are granted access to external services and how those grants are
stored.
## Requirements
### Requirement: Per-agent OAuth connector binding store

系统 SHALL 在一张专用授权 join 表 `agent_service_grants`（重命名自 `agent_oauth_bindings`）中持久化「哪个 agent 被授权使用哪个外部服务」。该表 SHALL 以 `(agent_id, service_id)` 为主键，并携带 `run_as`（`user` | `agent`，默认 `user`）以声明工具调用时取**调用用户**还是**该 agent 自身 principal** 的凭证。store SHALL 暴露 `bind(agent_id, service_id, created_by=None)`、`unbind(agent_id, service_id)`、`list_services_for_agent(agent_id) -> list[str]`、`list_agents_for_service(service_id) -> list[int]`。绑定 SHALL 对 `(agent_id, service_id)` 幂等。SQL MUST 用 named parameters 经 store 边界；schema MUST 由迁移建立，并保留 `FK agent_id→agents.id ON DELETE CASCADE`（使 `delete_agent` 仍仅 `DELETE FROM agents` 即级联清理）；无 ORM。旧模块路径 `agent_oauth_binding_store` MUST 保留 re-export shim（不承载逻辑）。

#### Scenario: Bind then list is idempotent
- **WHEN** `bind(5, "github")` is called twice
- **THEN** `list_services_for_agent(5)` returns `["github"]` exactly once

#### Scenario: Unbind removes the binding
- **WHEN** a service is bound to an agent and then `unbind(agent_id, service_id)` is called
- **THEN** `list_services_for_agent(agent_id)` no longer contains that service_id

#### Scenario: Binding is scoped per agent
- **WHEN** `bind(5, "github")` and `bind(7, "github")` are called
- **THEN** `list_agents_for_service("github")` returns both agent ids and each agent lists `github`

#### Scenario: run_as 默认为 user
- **WHEN** 以 `bind(5, "github")` 建立绑定而未显式指定 run_as
- **THEN** 该 grant 的 `run_as` 为 `user`（dispatch 解析凭证时取调用用户的凭证）

#### Scenario: Migration creates and renames the table
- **WHEN** Alembic upgrades to head on a database that has the legacy `agent_oauth_bindings` table
- **THEN** the table is renamed to `agent_service_grants` with columns for agent_id, service_id, run_as, created_at, created_by, its rows preserved, and `FK agent_id→agents.id ON DELETE CASCADE` retained

#### Scenario: 删除 agent 级联清理 grant
- **WHEN** 一个有 `agent_service_grants` 绑定的 agent 被 `delete_agent` 删除
- **THEN** 该 agent 的所有 grant 行经 FK CASCADE 被清理，无孤儿行

### Requirement: Admin 授权 agent 使用服务并设置 run_as

管理面 SHALL 允许 admin 为某 agent 绑定 / 解绑可用外部服务，并在绑定时设置 `run_as`（`user` | `agent`，默认 `user`）。main 上现有路由为 `/admin/agents/{name}/bindings/oauth`；本 phase SHALL 保留该路径兼容面，但底层改接 P0 已落地的 `agent_service_grant_store`，不再走 legacy `agent_oauth_binding_store` 语义。该面 SHALL 能列出某 agent 已授权的服务及其 `run_as`、以及某服务已授权的 agent。绑定写入经 `agent_service_grants` store，对 `(agent_id, service_id)` 幂等。仅 admin 可写，viewer 只读（403）。写操作 SHALL 落审计。

#### Scenario: Admin 绑定服务并设 run_as
- **WHEN** admin 为 agent `sales` 绑定服务 `github` 并设 `run_as="user"`
- **THEN** `GET /admin/agents/sales/bindings/oauth` 返回一条 `service_id=github` 的 grant，且其 `run_as` 为 `user`，操作落审计

#### Scenario: 设 run_as=agent
- **WHEN** admin 为 agent `ops` 绑定服务 `internal-kb` 并设 `run_as="agent"`
- **THEN** 该 grant 的 `run_as` 为 `agent`（dispatch 时取该 agent principal 的凭证）

#### Scenario: 解绑移除授权
- **WHEN** admin 解绑 agent `sales` 的服务 `github`
- **THEN** `sales` 的已授权服务列表不再含 `github`

#### Scenario: 可查看某服务已授权的 agent
- **WHEN** admin 查询服务 `github` 的授权对象
- **THEN** 返回所有已绑定该服务的 agent 列表

#### Scenario: Viewer 不能改授权
- **WHEN** viewer 尝试 bind / unbind 任一 agent 的服务
- **THEN** 请求被 403 拒绝

### Requirement: run_as=agent 解析生效

`agent_service_grants.run_as="agent"` 的绑定在 dispatch 时 SHALL 解析为该 agent 的 service-principal 凭证（见 `agent-service-principal`），而非调用用户的凭证。`run_as="user"`（默认）行为不变。run_as 的取值 SHALL 仅由 grant 承载，MUST NOT 暴露为 LLM 可见的工具参数。

#### Scenario: run_as=agent 走 agent principal
- **WHEN** agent `ops` 对服务 `internal-kb` 的 grant `run_as="agent"`，`ops` 调用对应工具
- **THEN** 凭证以 `ops` 的 service-principal 解析，调用用户身份不参与该次凭证解析

#### Scenario: run_as 不进 LLM schema
- **WHEN** 对声明 connector 的工具调用 `get_schemas()`
- **THEN** 返回 schema 不含 `run_as` 信息

