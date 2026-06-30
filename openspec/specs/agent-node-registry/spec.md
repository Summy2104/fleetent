# agent-node-registry Specification

## Purpose
Define the management-plane registry for agent runtime nodes, including node identity,
service-key authentication, and operator-driven registration lifecycle.
## Requirements
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

系统 SHALL 通过 `fleetent platform`（bootstrap/ops 入口）提供 node 登记、列举、注销命令——node 登记属基础设施运维动作，先于 / 独立于平台业务管理。

#### Scenario: 通过 platform CLI 登记 node

- **WHEN** 运维执行 `fleetent platform node register <node-id>`
- **THEN** 系统登记该 node 并打印一次性 service key（提示妥善保存）

#### Scenario: 标签随登记记录（v1 不消费）

- **WHEN** 登记时附带 `--label key=value`
- **THEN** 标签以 JSON 持久化于 `nodes` 表，供未来调度使用；v1 不据其做任何匹配

### Requirement: node 管理 admin HTTP API

系统 SHALL 在 `/admin/nodes` 下暴露管理员可用的 HTTP API，覆盖 node 注册、列举、注销、pin 与 unpin。所有端点 SHALL 使用 `Authorization: Session <token>` 做管理员鉴权，而不是 node 自身的 Bearer service key。底层操作 SHALL 复用 `node_store` 与 `placement_store`，与 `fleetent platform node` CLI 保持功能等价。注销成功 SHALL 返回 204；unpin 成功 SHALL 返回 204。注销仍有 pinned agent 的 node 时，409 响应体 SHALL 列出被 pin 的 agent（供运维知道需先解除哪些 pin）。

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

### Requirement: node service key 持久化失败必须暴露

登记 node 时，系统除哈希存储 service key（用于入站 node→platform 鉴权）外，还 SHALL 持久化
该 key 的可解密副本（经 secret store 加密），供 platform→node 出站鉴权（拨 node forwarder）使用。
该持久化 MUST NOT 被静默吞掉：当持久化失败（如缺 master key、secret 后端异常）时，系统 SHALL
log 明确错误并使登记**整体失败**，MUST NOT 返回一次性明文 key、报告"登记成功"却留下无法被
platform 取用的 node。

#### Scenario: 持久化失败则登记失败而非假成功

- **WHEN** 登记 node 时 service key 的可解密持久化失败（例如 master key 缺失）
- **THEN** 系统 log 明确错误并使该次登记失败（抛出可诊断错误）
- **AND** 不返回一次性明文 key、不在 `nodes` 表留下一个 platform 永远拨不通的 node

#### Scenario: 持久化成功则 platform 可取用 key

- **WHEN** 登记成功且 master key 就绪
- **THEN** platform 后续可解密取回该 node service key，用于向其 forwarder 出站鉴权

### Requirement: platform→node 转发寻址按可达地址优先

platform 拨 node forwarder（转发 agent chat / WS）时，目标 host SHALL 按以下优先级解析，端口（8786）与协议（http / ws）不变：

1. 该 node 持久化的 `forward_host`（node 经心跳上报）——最高优先；
2. 环境变量 `FLEETENT_FORWARDER_HOST_OVERRIDE`（全局覆盖）；
3. `{node_id}.internal` 约定（兜底，依赖部署环境外部 DNS）。

此优先级 SHALL 在 platform 侧实现（读 platform 自有的 node 注册表），MUST NOT 使 node 运行时模块依赖管理库。未上报地址的 node SHALL 自动回落到 override 或 `.internal` 约定，保持既有行为。

node 上报的 `forward_host` 由 node 自报并被拼入拨号 URL，因此在用于拨号前 SHALL 校验为合法的 IPv4 字面量或 RFC-1123 主机名。含 URL 走私字符（`@`、`/`、`?`、`#`、`:`、空白等）的值 SHALL 被拒绝并回落到 override / `.internal`（防 SSRF：避免被引导拨向非预期 host）。loopback / 内网地址（如 `127.0.0.1`、`10.x`）合法放行——同机 / 内网部署正是主用法。

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

#### Scenario: 拒绝非法上报地址（防 SSRF）

- **WHEN** 某 node 的 `forward_host` 含非主机名字符（如 `evil.com/path`、`node-a@evil.com`、带端口或空白）
- **THEN** platform 忽略该值并回落到 override / `{node_id}.internal`，不据此拨号
- **AND** loopback / 内网地址（如 `127.0.0.1`、`10.38.8.143`）视为合法，正常用于拨号

