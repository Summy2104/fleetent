## Context

C1–C4 已落地（C4 apply-ready）：分机编排的声明式期望态（C2 desired-state API + status 过滤）+ node supervisor 调谐（C3 reconcile，PID 真相/幂等/崩溃重拉）+ secret 注入（C4）。旧的进程控制——`lifecycle_admin_api`（`/start`、`/stop`、`/runtime-status`）+ 内存 `AgentController`——已被完整取代。C5 拆掉它，并清掉同源死函数 `agent_routing_status`。

当前 main 核实：
- `lifecycle_admin_api.py` **仅含** start/stop/runtime-status，挂在 `server.py:301`。
- `AgentController`(`controller.py`) 调用者仅 `lifecycle_admin_api` + `test_agent_controller`(unit) + `test_lifecycle_logging`(unit) + `test_lifecycle_admin_api`(integration)。
- `agent_routing_status`(`server.py:460`) **仍零生产调用**，仅 4 处测试引用。

## Goals / Non-Goals

**Goals:**
- 删 `lifecycle_admin_api.py`（+ server.py:36 import、:301 挂载）、`controller.py`（`AgentController`）、`agent_routing_status`。
- 清理对应测试（test_lifecycle_admin_api / test_agent_controller / test_lifecycle_logging 的 controller&api 部分 / agent_routing_status 的测试引用）。
- spec：REMOVE platform-agent-lifecycle 的 start/stop 需求 + agent-lifecycle-logging 的 controller/api 两条。

**Non-Goals:**
- **不动 `agent_admin_state.status` 与 `agent-lifecycle-toggle`**：enable/disable/archive 是 desired-state 输入（C2 已接线），保留。
- 不动 materialize（platform-agent-lifecycle 的物化需求保留）。
- 不动 node/（C3/C4）。

## Decisions

1. **整文件删 lifecycle_admin_api**：它仅含被淘汰的 start/stop/runtime-status，无其它内容 → 整文件删 + 去 server 的 import/挂载。

2. **runtime-status 由 node 实际态上报取代**：`/runtime-status`（platform 自己 spawn 追踪的"在跑吗"）语义已由 C2 `POST /nodes/{id}/status` + `node_agent_status` 投影取代——"是否在跑"读 node 上报，不再由 platform 自查内存。

3. **死函数 agent_routing_status 一并清**：全仓零生产调用、status 已由 C2 成真期望态，它彻底过时。无 capability、无 spec delta，仅删函数 + 4 处测试引用（含整文件 `test_agent_identity_phase3_routes.py` 若其仅测此函数）。

4. **agent-lifecycle-toggle 严格不碰**：必须确认本 change 不误删 enable/disable/archive 路径——那是 desired-state 的输入源，删了 C2/C3 就空转。

## Risks / Trade-offs

- **BREAKING（对外 API）**：依赖 `/admin/agents/{name}/start|stop|runtime-status` 的调用方（脚本/UI/askit）会 404。迁移路径：改 status + 读 node 上报。需 grep UI(`admin.html`)/脚本是否有调用方，一并改或在 proposal 标注。
- **测试基线**：删测试要确认删的是"测被删能力"的测试，不误伤；收尾对照 main 基线"无新增失败"。
- **误删 toggle 风险**：lifecycle 目录里 toggle 与 controller 混居，删时严格只删 controller/api，保 toggle。
- **前置依赖**：必须在 C3（reconcile 替代）已 apply 落 main 后执行——已满足。C4 不阻塞 C5（secret 与启停拆除正交），但建议 C4 先落以免基线交叉。
