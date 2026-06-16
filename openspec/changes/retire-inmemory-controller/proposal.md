> ⏳ **骨架（skeleton）**：本 change 仅 `proposal.md`。`specs/` 与 `tasks.md` 留待 JIT。
> 属**编排序列 C5/5**（收尾纯减法）。依赖：[`node-supervisor`]（替代到位后才能拆旧）。

## Why

旧的进程控制是 `lifecycle_admin_api` 的 start/stop/runtime-status + 一个**内存记 PID 的 `AgentController`**：明文不健康检查、不重启、不监管，platform 重启留孤儿。C3 的 reconcile（声明式期望态 + PID 真相 + 幂等调谐）已**完整替代**它。本 change 把这套脆弱的旧机制拆掉，并顺手清掉同源的死函数——收口"status×controller 两个开关概念不相连"的历史包袱。

## What Changes

- **移除 in-memory controller**：删 `platform/agent_lifecycle/controller.py`（`AgentController`）。
- **移除/改写 `lifecycle_admin_api`**：去掉 `POST /admin/agents/{name}/start`、`/stop`、`GET /runtime-status`（进程控制改为 reconcile）。runtime-status 的"在跑吗"由 C2 的**实际态上报**取代（platform 读 node 上报，而非自己 spawn 追踪）。
- **删死函数 `agent_routing_status`**（`server.py`）：全仓零生产调用的 advisory 残留，status 已由 C2 成为真期望态，它彻底过时。
- 清理上述的相关测试（start/stop/runtime-status、agent_routing_status）。
- 不做：不碰 `agent_admin_state.status`（它已在 C2 升格为期望态，保留）；不碰 C3 的 reconcile。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `platform-agent-lifecycle`: REMOVE 需求"Start and stop agent processes without monitoring"（start/stop/runtime-status + AgentController）；该能力其余（materialize 物化 home/.env/skills）保留。生命周期收敛为"声明期望态（C2）+ node 调谐（C3）"。
- `agent-lifecycle-logging`: REMOVE 需求"agent_lifecycle.controller 记录进程启停事件" + "agent_lifecycle.api 记录管理 API 调用"（对应模块删除）；保留"materialize 记录物化操作结果"。

> 注：`agent-lifecycle-toggle`（enable/disable/archive）**不动**——它是 desired-state 的输入（C2 已接线），保留。死函数 `agent_routing_status` 无 capability，删除属 impl+test 清理、无 spec delta。本 proposal 已对当前 main 核实删除目标与调用者（lifecycle_admin_api 仅含 start/stop/runtime-status；AgentController 调用者仅该 api + 2 测试；agent_routing_status 仍零生产调用）。

## Impact

**owning package**：platform（`agent_lifecycle/`、`server.py`）。**纯减法**。

**public API surface（移除）**：`/admin/agents/{name}/start|stop`、`/runtime-status` 端点；`AgentController`；`server.agent_routing_status`。

**owned tables**：无（不动 schema）。

**config namespace**：无。

**cross-module dependencies**：移除后 platform 不再 spawn agent 子进程（该职责整体移交 `node/`）；确认无其它调用者依赖被删端点/函数（`agent_routing_status` 已验证全仓零生产调用）。

**migration / shim plan**：无 schema/迁移。被删端点属对外 API 变更——**BREAKING**：依赖 start/stop/runtime-status 的调用方需改用声明式 status + node 上报。被删符号在 src 内的导入者随之清理；无需 re-export shim（非平铺模块搬迁，是能力下线）。

**前置**：必须在 C3（node reconcile）上线后执行，否则丢失启停能力。

**不碰**：`data-model.md`、主 specs（delta 写 change 内）。
