# agent-node-registry Specification

## Purpose
Define the management-plane registry for agent runtime nodes, including node identity,
service-key authentication, and operator-driven registration lifecycle.
## Requirements
### Requirement: node 注册表与身份

系统 SHALL 在管理库维护一张 `nodes` 表，记录每个 agent 运行节点的身份与登记元数据。表 SHALL 仅由 Alembic 维护（双权威：管理表不在 store 内 `_init_db()` 建表）。每个 node 由一个**运维选定的稳定 TEXT 标识**（node-id）主键唯一标识。node SHALL 携带一个**哈希存储的 service key**（明文为 `ma-<hex>`，仅登记时返回一次），用于 node↔platform 鉴权。

#### Scenario: 登记产生 node 与一次性 service key

- **WHEN** 运维登记一个新 node-id
- **THEN** 系统在 `nodes` 表插入该 node，生成 `ma-<hex>` service key，**仅以哈希持久化**（不存明文）
- **AND** 明文 service key 仅在本次登记响应中返回一次

#### Scenario: 重复 node-id 拒绝

- **WHEN** 登记一个已存在的 node-id
- **THEN** 系统拒绝并报冲突，不覆盖既有 node 或其 key

#### Scenario: node service key 解析为 node 身份

- **WHEN** 以有效 `ma-<hex>` service key 请求
- **THEN** 系统将其解析为对应 node 身份；key 无效或已注销时解析失败

### Requirement: node 列举与注销

系统 SHALL 提供列举所有已登记 node 与注销指定 node 的能力。注销一个仍有 agent 被 pin 的 node SHALL 被拒绝（保护性约束，避免静默使 agent 失去归属）。

#### Scenario: 列举 node

- **WHEN** 请求列举 node
- **THEN** 系统返回所有已登记 node 的 node-id、登记时间、标签与最近一次心跳时间（`last_seen_at`，未上报时为空）

#### Scenario: 注销空闲 node

- **WHEN** 注销一个没有任何 agent pin 在其上的 node
- **THEN** 系统删除该 node 记录

#### Scenario: 拒绝注销仍被占用的 node

- **WHEN** 注销一个仍有 agent pin 在其上的 node
- **THEN** 系统拒绝并报冲突，提示需先解除该 node 上的 agent pin

### Requirement: node 登记的运维入口

系统 SHALL 通过 `fleetent admin`（bootstrap/ops 入口）提供 node 登记、列举、注销命令——node 登记属基础设施运维动作，先于 / 独立于平台业务管理。

#### Scenario: 通过 admin CLI 登记 node

- **WHEN** 运维执行 `fleetent admin node register <node-id>`
- **THEN** 系统登记该 node 并打印一次性 service key（提示妥善保存）

#### Scenario: 标签随登记记录（v1 不消费）

- **WHEN** 登记时附带 `--label key=value`
- **THEN** 标签以 JSON 持久化于 `nodes` 表，供未来调度使用；v1 不据其做任何匹配

### Requirement: node 管理 admin HTTP API

系统 SHALL 在 `/admin/nodes` 下暴露管理员可用的 HTTP API，覆盖 node 注册、列举、注销、pin 与 unpin。所有端点 SHALL 使用 `Authorization: Session <token>` 做管理员鉴权，而不是 node 自身的 Bearer service key。底层操作 SHALL 复用 `node_store` 与 `placement_store`，与 `fleetent admin node` CLI 保持功能等价。

#### Scenario: 管理员通过 HTTP 注册 node

- **WHEN** admin 调用 `POST /admin/nodes`，提交 `node_id` 及可选 `name` / `labels`
- **THEN** 系统创建 node，并在响应中一次性返回 `service_key_plaintext_once`
- **AND** 响应不暴露持久化的 `key_hash`

#### Scenario: 管理员列举 node

- **WHEN** admin 调用 `GET /admin/nodes`
- **THEN** 系统返回所有已注册 node 的列表，包含 `id`、`name`、`labels` 与 `last_seen_at`

#### Scenario: 管理员注销空闲 node

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}`，且该 node 没有 pinned agent
- **THEN** 系统注销该 node 并返回成功响应

#### Scenario: 管理员不能注销仍有 pin 的 node

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}`，但该 node 仍有 pinned agent
- **THEN** 系统返回 409 Conflict，提示需先解除 pin

#### Scenario: 管理员 pin 与 unpin agent

- **WHEN** admin 调用 `POST /admin/nodes/{node_id}/pin` 指定 `agent_id`
- **THEN** 系统将该 agent pin 到对应 node

- **WHEN** admin 调用 `DELETE /admin/nodes/{node_id}/pin?agent_id=<id>`
- **THEN** 系统解除该 agent 的 node pin

#### Scenario: 非 admin 请求被拒绝

- **WHEN** viewer 角色用户调用任意 `/admin/nodes` 写端点
- **THEN** 系统返回 403
