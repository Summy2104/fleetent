## Why

`model_router.py` 按 `task_type` 查 `ROUTES` 表得到 `RouteConfig`（含 `model` + fallback 链），路由决策完全**静态**：只看 task_type，不看「现在还剩多少预算」。`docs/capabilities/model-router.md`「规划中（v1.0）」明确列出待实现项：

> - [ ] **成本感知路由**：当月成本已接近预算上限时，自动降级到 cheap task_type

与此同时，波次 3 的兄弟 change `cost-budget-control`（capability `agent-cost-budget`，AR18 五层成本预算）已 propose：它在 AR2（`budget.py`）单运行计量之上引入 per-task / per-session / per-user / per-agent / global 五层累计预算，并把剩余额度跨运行落盘。这意味着「当前预算剩余」已成为**可读取的运行时状态**——但 `model_router` 目前无从感知，无法据此调整路由倾向。

本 change（MR2）让路由**感知成本**：在不改 `model_router` 既有 task_type→provider 查表与 fallback 语义的前提下，引入一层「成本感知决策」，消费 AR18 暴露的预算剩余，据预算紧张程度把路由**倾向更便宜的模型**（如预算接近上限时降级到运维显式配置的低成本 target task_type）。预算充裕时行为与现状完全等价。

## What Changes

- 引入**成本感知策略** `CostAwareRoutingPolicy`：输入「预算剩余信号」+ 候选 `RouteConfig`，输出一个倾向更便宜模型的路由决策（保持 `model_router` 既有路由产物形态——`RouteConfig` / `RouteOverride`，不另造路由结果类型）。
- **消费预算剩余信号** `BudgetHeadroom`（只读快照）：表达「最紧的那一层」当前剩余比例 / 是否进入降级阈值（`cost_usd` 维度为主）。`BudgetHeadroom` 类型与生产它的 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 函数均**归 `cost-budget-control`(AR18) 拥有**（AR18 复用自己的五层迭代算「最紧层剩余比例」，是 `LayeredBudgetChecker` 找「最紧超限维度」的对偶）。本 change **从 AR18 import `BudgetHeadroom` 类型并消费其标量产出，不在 `cost_aware_routing.py` 定义该类型、不在 agent_loop 自算 headroom**。
- 引入**降级档位映射**：把「预算紧张级别」映射到「成本倾向动作」——`normal`（不干预，等价现状）/ `degrade`（改路由到运维显式配置的低成本 target task_type）。两档，具体阈值在 design 钉死，全部可配置、缺省**不干预**（向后兼容）。
- **决策入口下沉为按次传入**：成本感知在 `model_router` 取得 task_type route 之后、构造 client 之前，以一个可选的 `BudgetHeadroom` 入参（或注入的 policy 钩子）介入；agent_loop 瘦编排——调用 AR18 的 `headroom(...)` 拿标量后传入 `model_router`，自己不重算层级。未传入信号时路由行为与现状**逐字节等价**。
- 新增 `Settings` 字段承载降级阈值与开关（env-first，沿用既有命名惯例），缺省关闭（headroom 为 None 等价不启用）。

## Capabilities

### New Capabilities
- `cost-aware-routing`: 在 `model_router` 既有 task_type→provider 路由之上引入成本感知决策——消费 AR18 暴露的预算剩余，按预算紧张程度把路由倾向更便宜的模型（降级到运维显式配置的低成本 target task_type），预算充裕或未启用时与现状等价。

### Modified Capabilities
<!-- 不修改既有 spec。model_router 的 task_type 路由 / fallback 链 / client 构造契约作为依赖被引用、不改其语义；AR18 的 BudgetHeadroom 类型与 headroom() 生产者作为依赖被消费、归 AR18 所有。本 change 全部能力为新增，落在新 capability cost-aware-routing 下以 ADDED 表达。 -->

### 共享资源引用
- **`model_router.py` 路由产物 owner = MR1**：本 change 不改 `RouteConfig` / `RouteOverride` 结构、不改 `get_(async_)client_and_config` 既有语义，仅在其取得 route 后**追加**一层可选的成本感知决策；未传入预算信号时旁路。
- **AR18 预算剩余（`agent-cost-budget`）**：本 change 消费 AR18 暴露的「层级累计 vs 上限」的剩余快照——`BudgetHeadroom` 类型与 `headroom()` 生产者均归 AR18 拥有，本 change 仅 import 类型并消费其标量产出，不自行累计、不落盘、不重算层级。

## Impact

- **代码**：
  - 新增 `src/fleetent/cost_aware_routing.py`：从 `cost-budget-control`(AR18) **import `BudgetHeadroom` 类型**（不在本模块定义）、`CostAwareRoutingPolicy`（阈值→降级动作映射，两档 normal/degrade）、`from_settings` 构造。
  - 修改 `src/fleetent/model_router.py`：在 task_type route 解析后、client 构造前，接受可选 `BudgetHeadroom` 并经 policy 调整 route（旁路兼容）。具体接线在 design 钉死，不改既有路由/fallback 语义。
  - 修改 `src/fleetent/config.py`：新增成本感知阈值/开关字段（缺省关闭，向后兼容）。
- **配置**：新增成本感知开关、降级阈值与 `degrade_target` 字段，全部可选，缺省不干预（`degrade_target` 缺省 None，未显式配置时 degrade 档不可用、退回 normal）。
- **测试**：新增 `tests/test_cost_aware_routing.py`（消费 AR18 的 `BudgetHeadroom`、阈值→两档动作映射、degrade 改 task_type 解析、缺省旁路、未配 target 时 degrade 退回 normal）；扩充 `tests/test_model_router.py` 断言「无 headroom 时路由与现状等价」「预算紧张时降级到显式配置的低成本 route」。LLM / client 构造 mock，yaml 路径 monkeypatch 到 tmp_path。
- **不影响**：`model_router` 既有 task_type 路由 / fallback 链 / override 合并语义（仅旁路追加）、AR18 累计逻辑、agent_loop 主循环（仅瘦编排调用 AR18 `headroom()`）；不引入新依赖（`dataclasses` 已在用）。

## Dependencies

- **`src/fleetent/model_router.py`（MR1，已实现）**：复用 task_type→`RouteConfig` 查表、`RouteOverride` 字段合并、fallback 链语义、`get_(async_)client_and_config` 入口。本 change **不改其路由语义**，仅在 route 解析后追加成本感知决策。
- **`cost-budget-control`（AR18，本波次 3 已 propose，capability `agent-cost-budget`）**：AR18 **提供 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 生产者与 `BudgetHeadroom` 类型**（复用其五层迭代算最紧层 `cost_usd` 剩余比例），本 change **消费**这一标量。依赖方向 cost-aware-routing → cost-budget-control（路由依赖预算，自然方向）。agent_loop 调用 AR18 的 `headroom()` 后把标量传入 `model_router`，不重算层级。两者解耦（无 AR18 信号时本 change 旁路）。degrade 走运维显式配置的 target task_type、不需在本 change 比价择模型，故**不依赖 `budget.py` 单价表**。
