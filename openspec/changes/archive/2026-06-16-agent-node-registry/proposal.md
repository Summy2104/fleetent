> ⏳ **骨架（skeleton）**：本 change 仅 `proposal.md`（why / what / 模块边界）。`specs/` 与 `tasks.md` 留待 JIT——apply 前再补，以便带着实现经验定稿。
> 属**分机 agent 运行时编排序列 C1/5**。依赖：无（数据基座，解锁 C2）。下游：[`node-desired-state-api`]。

## Why

fleetent 支持 agent 运行时与 platform **分机部署**（独立 `install-agent.sh`，无 platform/alembic）。要做"platform 独立 + N 个 agent node"的编排，platform 必须先有一张**底账**：有哪些 node、每个 agent 被钉在哪个 node 上跑。这是整个编排序列的数据基座——本 change 只立模型与登记/钉绑入口，不引入任何运行时行为。

## What Changes

- **新增 `nodes` 管理表**：node 身份（node-id）、service key（node↔platform 鉴权凭证，复用 `ma-` bearer 体系）、手动登记元数据、`labels`（未来调度用，v1 不消费）、心跳/last-seen 字段。
- **新增 agent→node 显式 pin（placement）**：一个 agent 钉在**恰好一个** node 上（agent 是有状态单例，握 IM socket/独占 DB，非副本）。以独立 placement 表承载（保持 agent 定义纯净，placement 是运营态）。
- **登记/钉绑入口**：
  - node 登记（infra ops）→ `fleetent-admin node register|list|deregister`（属 bootstrap/ops 桶）。
  - agent→node pin（运营管理）→ HTTP API + 网页后台（与其它 agent 管理一致）。
- 不做：自动调度、label selector 匹配、failover 重分配（均列编排 roadmap）；不消费 status（C2 才消费）；无 reconcile 行为。

## Capabilities

### New Capabilities
- `agent-node-registry`: node 注册表 + 身份/service-key 鉴权 + 手动登记生命周期。
- `agent-node-placement`: agent→node 显式 pin（1 agent → 1 node），及其查询。

### Modified Capabilities
<!-- 无 -->

## Impact

**owning package**：platform（新 `platform/node_management/`）。

**public API surface（新增）**：node 注册/查询、agent placement 的 store 函数与 service interface（供 desired-state API 等 platform 内部消费）。

**owned tables（新增，管理库，Alembic 维护）**：`nodes`、`agent_placements`（或等价命名）。迁移号**不写死**，apply 时取当时序号。

**config namespace**：node 登记/鉴权相关（如 node service-key 校验）所属命名空间，apply 时定。

**cross-module dependencies**：读 `agent_store`（校验被 pin 的 agent 存在）；不反向被 agent runtime 依赖。

**migration / shim plan**：新增两张管理表，forward-only Alembic 迁移；无平铺模块搬迁、无 re-export shim。

**双权威遵从**：node/placement 属管理表 → 仅 Alembic 维护，不在 store 内 `_init_db()` 建表。

**不碰**：`data-model.md`、`openspec/specs/` 主 specs（delta 写 change 内）。
