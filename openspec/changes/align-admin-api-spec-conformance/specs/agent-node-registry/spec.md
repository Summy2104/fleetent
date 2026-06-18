## MODIFIED Requirements

### Requirement: node 管理 admin HTTP API

系统 SHALL 在 `/admin/nodes` 下暴露管理员可用的 HTTP API，覆盖 node 注册、列举、注销、pin 与 unpin。所有端点 SHALL 使用 `Authorization: Session <token>` 做管理员鉴权，而不是 node 自身的 Bearer service key。底层操作 SHALL 复用 `node_store` 与 `placement_store`，与 `fleetent-admin node` CLI 保持功能等价。注销成功 SHALL 返回 204；unpin 成功 SHALL 返回 204。注销仍有 pinned agent 的 node 时，409 响应体 SHALL 列出被 pin 的 agent（供运维知道需先解除哪些 pin）。

#### Scenario: 管理员通过 HTTP 注册 node

- **WHEN** admin 调用 `POST /admin/nodes`，提交 `node_id` 及可选 `name` / `labels`
- **THEN** 系统创建 node，并在响应中一次性返回 `service_key_plaintext_once`
- **AND** 响应不暴露持久化的 `key_hash`

#### Scenario: 管理员列举 node

- **WHEN** admin 调用 `GET /admin/nodes`
- **THEN** 系统返回所有已注册 node 的列表，包含 `id`、`name`、`labels` 与 `last_seen_at`

#### Scenario: 管理员注销空闲 node 返回 204

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}`，且该 node 没有 pinned agent
- **THEN** 系统注销该 node 并返回 204（无响应体）

#### Scenario: 管理员不能注销仍有 pin 的 node，409 列出被 pin agent

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}`，但该 node 仍有 pinned agent
- **THEN** 系统返回 409 Conflict，响应体列出被 pin 的 agent（如 `pinned_agents`），提示需先解除 pin

#### Scenario: 管理员 pin 与 unpin agent

- **WHEN** admin 调用 `POST /admin/nodes/{node_id}/pin` 指定 `agent_id`
- **THEN** 系统将该 agent pin 到对应 node

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}/pin?agent_id=<id>`
- **THEN** 系统解除该 agent 的 node pin 并返回 204

#### Scenario: 非 admin 请求被拒绝

- **WHEN** viewer 角色用户调用任意 `/admin/nodes` 写端点
- **THEN** 系统返回 403
