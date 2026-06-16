# node-desired-state-api Specification

## Purpose
TBD - created by archiving change node-desired-state-api. Update Purpose after archive.
## Requirements
### Requirement: node 鉴权

系统 SHALL 用 node service key（C1 `nodes.key_hash`）鉴权 node 的所有期望态/上报请求。请求 SHALL 携带 `Authorization: Bearer ma-<hex>`，经 `node_store.resolve_node_key` 解析为 node 身份；解析失败 SHALL 拒绝（401）。一个 node SHALL 只能访问/上报**自己**（URL 中的 `{id}` 必须等于其 key 解析出的 node-id），跨 node 访问 SHALL 拒绝（403）。

#### Scenario: 有效 node key 通过且仅限自身

- **WHEN** node 以其 service key 请求 `/nodes/{自身id}/...`
- **THEN** 系统接受并在该 node 作用域内执行

#### Scenario: 无效 key 拒绝

- **WHEN** 请求携带缺失或不匹配 `nodes.key_hash` 的 key
- **THEN** 系统返回 401，不进入业务逻辑

#### Scenario: 跨 node 访问拒绝

- **WHEN** node A 的 key 请求 `/nodes/{B 的 id}/...`
- **THEN** 系统返回 403

### Requirement: 分区期望态拉取

系统 SHALL 暴露 `GET /nodes/{id}/desired-state`，返回该 node 应运行的 agent 集合及其下发配置。集合 SHALL 满足：

- **按 placement 分区**：只含 pin 到该 node 的 agent（C1 `placement_store.list_by_node`）。
- **按 status 过滤**：只含 `agent_admin_state.status == "enabled"` 的 agent；`disabled` / `archived` SHALL NOT 出现。这是 status **第一次真正生效**的接线点。
- **携带 materialized 配置**：每个 agent 附其下发用配置载荷（复用 `materialize.agent_file_from_store` 产出 agent.yaml 内容，**序列化进响应、不写本地盘**）。本 change 的配置载荷为**非密**部分；secret 由后续 change（`node-secret-delivery`）扩展。

#### Scenario: 只返回本 node 且 enabled 的 agent

- **WHEN** node 拉取期望态，其上 pin 了 agentA(enabled)、agentB(disabled)、agentC(archived)
- **THEN** 响应只含 agentA；agentB、agentC 不出现

#### Scenario: 每个 agent 附配置载荷

- **WHEN** 期望态返回 agentA
- **THEN** agentA 条目含其 materialized agent.yaml 内容（非密字段），node 据此可写本地 home

#### Scenario: 空归属返回空集

- **WHEN** node 上没有任何 enabled 的 pin agent
- **THEN** 响应返回空 agent 集合（非错误）

### Requirement: 实际态上报与心跳

系统 SHALL 暴露 `POST /nodes/{id}/status`，接收 node 上报的**实际态**（其上各 agent 是否在跑 / PID / 健康）与心跳。上报 SHALL 更新该 node 的 `nodes.last_seen_at`（C1 已建该列），并 SHALL 持久化 per-agent 实际态供控制台/可观测读取。实际态是**只读投影**（控制真相在 node 的 PID 文件），platform 不据其做控制决策。

#### Scenario: 心跳刷新 last_seen_at

- **WHEN** node POST 上报
- **THEN** 系统将该 node 的 `last_seen_at` 更新为当前时间

#### Scenario: per-agent 实际态可被查询

- **WHEN** node 上报 agentA running(pid=123) 后，控制台查询该 node 实际态
- **THEN** 返回 agentA running/pid 等已上报字段

#### Scenario: 上报受 node 鉴权与自限约束

- **WHEN** 上报请求的 key 无效或 `{id}` 非自身
- **THEN** 分别按 401 / 403 拒绝（同 node 鉴权要求）

