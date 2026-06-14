# agent-oauth-binding Specification

## ADDED Requirements

### Requirement: Admin 授权 agent 使用服务并设置 run_as

管理面 SHALL 允许 admin 为某 agent 绑定 / 解绑可用外部服务，并在绑定时设置 `run_as`（`user` | `agent`，默认 `user`）。该面 SHALL 能列出某 agent 已授权的服务、以及某服务已授权的 agent。绑定写入经 P0 的 `agent_service_grants` store，对 `(agent_id, service_id)` 幂等。仅 admin 可写，viewer 只读（403）。写操作 SHALL 落审计。

#### Scenario: Admin 绑定服务并设 run_as
- **WHEN** admin 为 agent `sales` 绑定服务 `github` 并设 `run_as="user"`
- **THEN** `sales` 的已授权服务列表含 `github`，其 grant 的 `run_as` 为 `user`，操作落审计

#### Scenario: 设 run_as=agent
- **WHEN** admin 为 agent `ops` 绑定服务 `internal-kb` 并设 `run_as="agent"`
- **THEN** 该 grant 的 `run_as` 为 `agent`（dispatch 时取该 agent principal 的凭证）

#### Scenario: 解绑移除授权
- **WHEN** admin 解绑 agent `sales` 的服务 `github`
- **THEN** `sales` 的已授权服务列表不再含 `github`

#### Scenario: Viewer 不能改授权
- **WHEN** viewer 尝试 bind / unbind 任一 agent 的服务
- **THEN** 请求被 403 拒绝
