## MODIFIED Requirements

### Requirement: node 注册表与身份

系统 SHALL 在管理库维护一张 `nodes` 表，记录每个 agent 运行节点的身份与登记元数据。表 SHALL 仅由 Alembic 维护（双权威：管理表不在 store 内 `_init_db()` 建表）。每个 node 由一个**运维选定的稳定 TEXT 标识**（node-id）主键唯一标识。node SHALL 携带一个**哈希存储的 service key**（明文为 `ma-<hex>`，仅登记时返回一次），用于 node↔platform 鉴权。

`nodes` 表 SHALL 含一列 `forward_host`（nullable TEXT），记录该 node 自报的、供 platform 出站拨号其 forwarder 的可达地址（IP 或主机名）。该列在登记时为空，由 node 心跳上报后填充（见 `node-supervisor`）；为空表示该 node 未上报地址。

#### Scenario: 登记产生 node 与一次性 service key

- **WHEN** 运维登记一个新 node-id
- **THEN** 系统在 `nodes` 表插入该 node，生成 `ma-<hex>` service key，**仅以哈希持久化**（不存明文）
- **AND** 明文 service key 仅在本次登记响应中返回一次
- **AND** 该 node 的 `forward_host` 初始为空（NULL）

#### Scenario: 重复 node-id 拒绝

- **WHEN** 登记一个已存在的 node-id
- **THEN** 系统拒绝并报冲突，不覆盖既有 node 或其 key

#### Scenario: node service key 解析为 node 身份

- **WHEN** 以有效 `ma-<hex>` service key 请求
- **THEN** 系统将其解析为对应 node 身份；key 无效或已注销时解析失败

#### Scenario: 持久化并取回 node 的可达地址

- **WHEN** 系统以一个 `forward_host` 值为某 node 调用 `set_forward_host`
- **THEN** 后续 `get_forward_host(node_id)` 返回该值
- **AND** 从未上报地址的 node，`get_forward_host(node_id)` 返回空（NULL）

## ADDED Requirements

### Requirement: platform→node 转发寻址按可达地址优先

platform 拨 node forwarder（转发 agent chat / WS）时，目标 host SHALL 按以下优先级解析，端口（8786）与协议（http / ws）不变：

1. 该 node 持久化的 `forward_host`（node 经心跳上报）——最高优先；
2. 环境变量 `FLEETENT_FORWARDER_HOST_OVERRIDE`（全局覆盖）；
3. `{node_id}.internal` 约定（兜底，依赖部署环境外部 DNS）。

此优先级 SHALL 在 platform 侧实现（读 platform 自有的 node 注册表），MUST NOT 使 node 运行时模块依赖管理库。未上报地址的 node SHALL 自动回落到 override 或 `.internal` 约定，保持既有行为。

#### Scenario: 已上报地址的 node 用持久化地址转发

- **WHEN** 某 node 的 `forward_host` 为 `10.38.8.143`，platform 向其转发 agent chat
- **THEN** platform 拨 `http://10.38.8.143:8786/...`，不解析 `{node_id}.internal`

#### Scenario: 未上报地址回落到约定

- **WHEN** 某 node 的 `forward_host` 为空，且未设 `FLEETENT_FORWARDER_HOST_OVERRIDE`
- **THEN** platform 回落拨 `http://{node_id}.internal:8786/...`（既有行为）

#### Scenario: override 在无上报地址时生效、低于上报地址

- **WHEN** 设了 `FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1`
- **THEN** 对**未上报** `forward_host` 的 node，platform 拨 `http://127.0.0.1:8786/...`
- **AND** 对**已上报** `forward_host` 的 node，platform 仍优先用其上报地址，不被 override 覆盖
