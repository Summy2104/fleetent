## ADDED Requirements

### Requirement: 节点管理 admin HTTP API

系统 SHALL 在 `/admin/nodes` 下暴露节点注册/注销/pin 的 HTTP API，供管理员操作，所有端点 MUST 要求 admin 角色（`Authorization: Session <token>`，区别于 node 自身的 Bearer service key 鉴权）。底层调用 `node_store` 和 `placement_store`，与 `fleetent-admin node` CLI 命令等价。

#### Scenario: 注册节点并获得一次性 service key

- **WHEN** admin 调用 `POST /admin/nodes`，body 含 `node_id`（及可选 `name`/`labels`）
- **THEN** 系统注册节点并在响应中返回 `service_key_plaintext_once`（`ma-<hex>` 明文，仅此一次）
- **AND** 后续查询不再返回明文 key（以哈希持久化）

#### Scenario: 重复 node_id 注册被拒绝

- **WHEN** admin 注册已存在的 `node_id`
- **THEN** 系统返回 409 Conflict，不覆盖现有节点

#### Scenario: 列举所有节点

- **WHEN** admin 调用 `GET /admin/nodes`
- **THEN** 系统返回所有已注册节点列表（含 `node_id`、`name`、`labels`、`last_seen_at`）

#### Scenario: 注销节点（无 pin 时成功）

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}`，且该节点无 agent pin
- **THEN** 系统删除节点注册，返回 204

#### Scenario: 注销有 pin 的节点被拒绝

- **WHEN** admin 尝试注销仍有 agent pin 的节点
- **THEN** 系统返回 409，响应体列出被 pin 的 agent，提示先 unpin

#### Scenario: pin agent 到节点

- **WHEN** admin 调用 `POST /admin/nodes/{node_id}/pin`，body 含 `agent_id`
- **THEN** 系统将指定 agent pin 到该节点

#### Scenario: unpin agent

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}/pin`，body 含 `agent_id`
- **THEN** 系统解除 pin，返回 204

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用任意节点管理端点
- **THEN** 系统返回 403
