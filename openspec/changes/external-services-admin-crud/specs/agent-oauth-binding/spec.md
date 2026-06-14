# agent-oauth-binding Specification

## ADDED Requirements

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
