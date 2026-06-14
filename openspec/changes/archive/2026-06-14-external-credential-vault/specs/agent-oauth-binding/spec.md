# agent-oauth-binding Specification

## MODIFIED Requirements

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
