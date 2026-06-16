> ⏳ **骨架（skeleton）**：本 change 仅 `proposal.md`。`specs/` 与 `tasks.md` 留待 JIT。
> 属**编排序列 C2/5**。依赖：[`agent-node-registry`]（node + placement 表）。下游：[`node-supervisor`]、[`node-secret-delivery`]。

## Why

这是整套编排的**承重契约**：分机 node 不能让 platform 反向伸手（边界铁律），所以 node 必须**主动拉**"我该跑哪些 agent + 它们的配置"。本 change 定义这个**位置透明、按 node 分区**的 API，并让 agent 的 **status 第一次真正生效**（只有 `enabled` 的 agent 进入期望态）。契约能脱离 node 独立测——先于 C3 落地，给 node 一个稳定靶子。

## What Changes

- **`GET /nodes/{id}/desired-state`**：按 placement 分区（只返回 pin 到该 node 的 agent）+ **按 `status` 过滤**（`enabled` 才返回；`disabled`/`archived` 不返回）+ 携带 **materialized 配置**（非密；secret 由 C4 扩展）。
- **`POST /nodes/{id}/status`**：node 上报**实际态**（在跑哪些 agent / PID / 健康）+ 心跳；platform 据此驱动控制台展示与 node 健康判定。
- **node 鉴权**：用 C1 的 node service-key 鉴权；node 只能拉/报**自己**分区的数据。
- **status → 期望态接线**：`agent_admin_state.status`（enabled/disabled/archived）在此被消费，成为 reconciler 的输入——**收口此前 park 的 status 决策**（enforce via 声明式期望态，而非 platform 入站拦截，不违反边界）。
- **materialize 产出可下发载荷**：今天 materialize 写本地盘；本 change 让其同时能产出**经 API 下发的配置载荷**，供 node 写本地 home。
- 不做：secret 下发（C4）；node 侧任何行为（C3）。

## Capabilities

### New Capabilities
- `node-desired-state-api`: node 鉴权 + 分区期望态拉取（按 placement 分区 + status 过滤 + 配置载荷）+ 实际态/心跳上报。

### Modified Capabilities
<!-- 细化时（C1 已落地）的修订：status 的 enable/disable/archive 行为本身不变，只是
     desired-state API 成为它的新消费者 → 按"新增行为不改既有"原则全部落在新 capability，
     不 modify agent-lifecycle-toggle。platform-agent-lifecycle 的 start/stop 拆除属 C5，
     C2 不碰。故本 change 无 Modified Capabilities。 -->
<!-- 无 -->

> 注：本 proposal 由 skeleton 细化（C1 `agent-node-registry` 已 apply 落地 main，迁移 096）。
> 本 change 对着 C1 真实产物写：`placement_store.list_by_node` / `node_store.resolve_node_key` /
> `nodes.last_seen_at` 列 / `materialize.agent_file_from_store`。

## Impact

**owning package**：platform（`platform/node_management/` 续建 + 触碰 `agent_lifecycle/materialize`）。

**public API surface（新增）**：`/nodes/{id}/desired-state`、`/nodes/{id}/status` 两个 HTTP 端点；materialize 的"产出可下发载荷"函数。

**owned tables**：无新增（用 C1 的 `nodes`/`agent_placements`、既有 `agent_admin_state`）。

**config namespace**：node 鉴权/心跳超时等所属命名空间，apply 时定。

**cross-module dependencies**：读 `agent_admin_store`（status）、`agent_store`（定义）、`agent_lifecycle.materialize`（配置载荷）、C1 的 node/placement store。不反向被 agent runtime 依赖。

**migration / shim plan**：无新表（可能给 `nodes` 加上报态字段，若需则 forward-only 迁移，号不写死）；无 shim。

**不碰**：`data-model.md`、主 specs（delta 写 change 内）。
