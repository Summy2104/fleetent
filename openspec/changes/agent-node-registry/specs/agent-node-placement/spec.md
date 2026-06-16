## ADDED Requirements

### Requirement: agent→node 显式 pin（1:1）

系统 SHALL 在管理库维护一张 `agent_placements` 表，把一个 agent **显式 pin 到恰好一个 node** 上运行。表 SHALL 仅由 Alembic 维护。约束：

- `agent_id` 为主键并 `FOREIGN KEY REFERENCES agents(id) ON DELETE CASCADE`——**一个 agent 至多一条 placement（1:1）**，agent 删除时其 placement 级联删除。
- `node_id` `FOREIGN KEY REFERENCES nodes(id)`，且 SHALL 阻止删除仍被引用的 node（与 node 注销保护一致）。

agent 是**有状态单例**（独占 IM 连接 / per-agent DB），SHALL NOT 被 pin 到多个 node（不做副本）。

#### Scenario: pin agent 到 node

- **WHEN** 把一个已存在的 agent pin 到一个已登记的 node
- **THEN** 系统在 `agent_placements` 记录该 (agent_id, node_id)；该 agent 后续出现在该 node 的归属集合中

#### Scenario: 重新 pin 覆盖（仍 1:1）

- **WHEN** 把一个已 pin 的 agent 改 pin 到另一个 node
- **THEN** 系统更新该 agent 的 placement 为新 node，旧归属不再保留（始终至多一条）

#### Scenario: pin 不存在的 agent 或 node 被拒

- **WHEN** pin 时 agent 或 node 不存在
- **THEN** 系统拒绝，不创建悬空 placement

#### Scenario: 解除 pin

- **WHEN** 对一个已 pin 的 agent 执行 unpin
- **THEN** 系统删除其 placement；该 agent 不再归属任何 node（成为未编排状态）

### Requirement: placement 查询

系统 SHALL 支持按 node 查询其归属的 agent 集合，以及按 agent 查询其当前 node。按 node 的查询为分区期望态（后续 change）提供归属轴。

#### Scenario: 按 node 列出归属 agent

- **WHEN** 查询某 node 的归属 agent
- **THEN** 系统返回 pin 到该 node 的全部 agent

#### Scenario: 按 agent 查其 node

- **WHEN** 查询某 agent 的 placement
- **THEN** 系统返回其当前 node-id，未 pin 时返回空
