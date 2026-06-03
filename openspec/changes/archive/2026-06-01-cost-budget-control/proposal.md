## Why

AR2（`budget.py`）已实现**单次运行**的三维预算计量（`turns` / `tokens` / `cost_usd`）：`BudgetConfig` 携带每次运行的上限、`BudgetUsage.add(...)` 是唯一累计入口、`BudgetChecker` 把「任一维度耗尽」接入 AR1 终止框架的 `StopReason.budget_exceeded`。但 AR2 的预算**只作用于一次 `run()`/`run_stream()`**——它无法表达「单个用户一天累计花多少」「整个部署全局成本上限」这类跨运行、跨 session 的治理需求。

`docs/capabilities/agent-runtime.md`「运行治理」明确要求**成本预算管控（五层）**：

> 单次任务 / 单 session / 单用户 / 单 agent / 全局，各自可配置上限；三个计量维度：执行步数 / token 用量 / 美元成本；系统内部操作（如压缩调用）可豁免计入预算；到达上限触发 Grace Call，不硬切断。

本 change 在 AR2 既有计量之上，引入**五层成本预算管控**：为 per-task / per-session / per-user / per-agent / global 五个层级各自维护可配置上限与累计用量，任一层级超限即经 termination 的 `budget_exceeded` 触发 Grace Call。**复用 `budget.py` 的维度集 `{turns, tokens, cost_usd}` 与单价换算口径，不重造计量**；本 change 只新增「层级聚合 + 跨运行累计持久化 + 多层超限判定」。

## What Changes

- 引入**五层预算层级** `BudgetScope` 枚举：`task` / `session` / `user` / `agent` / `global`，与 roadmap 五层一一对应。
- 引入**每层预算上限配置** `LayeredBudgetConfig`：每层一份 `BudgetConfig`（复用 AR2 的 `{max_turns, max_tokens, max_cost_usd}`，各维度 `NO_LIMIT=-1` 表无上限），未配置的层默认全 `NO_LIMIT`（不拦截，保向后兼容）。
- 引入**跨运行累计存储** `BudgetStore`（标准库 `sqlite3`，**不用 aiosqlite**）：以 `(scope, key, period)` 为主键累计 `turns/tokens/cost_usd`（`key` 为 user_id / agent_id / session_id，`global` 用固定哨兵），`period` 由**可注入时钟（UTC）**按该层窗口算出。累加用 `ON CONFLICT(scope, key, period) DO UPDATE` 原子完成。累计入口复用 `BudgetUsage.add(...)` 的口径——本 change 不重新实现单价换算。
- 引入**预算按窗口周期重置**：窗口取值集 `{lifetime, daily, weekly, monthly}`，`period` 入主键使跨周期累计天然落新行、从 0 起（**涌现式重置，不引入定时清零、不依赖调度器**）。各层默认窗口 `session`→`lifetime`、`user`/`agent`→`weekly`、`global`→`monthly`。
- 引入**跨运行层聚合检查器** `LayeredBudgetChecker`（实现 AR1 `TerminationChecker` 协议）：**只迭代 4 个跨运行层**（session/user/agent/global），按由窄到宽顺序检查每层当前周期累计是否触限，任一层超限即返回 `StopReason.budget_exceeded` 并记录**触发层级 + 触发维度**供 trace；`task` 层由 AR2 per-run `BudgetChecker` 承载，不重复判定、不另设配置。某层 `key` 缺失（纯 CLI 运行）时跳过该层。
- **系统内部操作豁免**：沿用 AR2「只有主循环推进任务的 LLM 调用走 `add`」的契约——压缩调用、Grace Call 自身不计入任何层级。
- **超限即 Grace Call**：复用 AR2 既有的 `budget_exceeded` → Grace Call 收尾路径，本 change 不重写 Grace Call 逻辑。
- 新增 `Settings` 字段承载跨运行层默认上限与窗口（env-first，沿用 `agent_max_*` 命名惯例）：`agent_budget_{session,user,agent,global}_{turns,tokens,cost_usd}` 上限，以及 `agent_budget_{user,agent,global}_window` 窗口（session 固定 `lifetime` 不可配；不含 `agent_budget_task_*`，task 归 AR2）。
- 暴露 `headroom()` + 只读值对象 `BudgetHeadroom` 供 `cost-aware-routing`（MR2）成本感知路由消费：返回当前最紧层的 cost 剩余比例（`cost_remaining_ratio`）与层名（`tightest_scope`）的**只读快照**，**复用本 change 五层迭代内核**（与 `LayeredBudgetChecker` 同一套层级遍历 + 上限对照），不改既有检查/累计/Grace Call 逻辑。类型与生产者落本 change（AR18），使依赖方向保持 MR2→AR18。

## Capabilities

### New Capabilities
- `agent-cost-budget`: 在 AR2 单运行计量之上引入 per-task / per-session / per-user / per-agent / global 五层成本预算（task 复用 AR2 per-run，session/user/agent/global 四层跨运行累计），各层可配置 `turns`/`tokens`/`cost_usd` 上限，跨运行层按日历翻滚窗口（`{lifetime,daily,weekly,monthly}`）周期重置，任一层超限经 `budget_exceeded` 触发 Grace Call。

### Modified Capabilities
<!-- 不修改既有 spec。AR2 的计量契约（budget.py 的 BudgetConfig/BudgetUsage/BudgetChecker）作为依赖被引用、不改其语义；本 change 全部能力为新增，落在新 capability agent-cost-budget 下以 ADDED 表达。 -->

### 共享资源引用
- **`config/settings.yaml` / `Settings`**：本 change 仅**追加**五层预算上限字段（`agent_budget_*`），不改既有 `agent_max_*`（AR2）。
- **`data/users.db`**：本 change 新增一张累计表（如 `budget_usage`），与既有表共处同库，独立 schema，不改既有表。

## Impact

- **代码**：
  - 新增 `src/fleetent/layered_budget.py`：`BudgetScope` 枚举、`BudgetWindow` 枚举、`LayeredBudgetConfig` 数据类、`BudgetStore`（`sqlite3` 累计持久化，主键含 `period`，可注入时钟，模块级 `DB_PATH` 可 monkeypatch）、`LayeredBudgetChecker`（4 个跨运行层聚合检查 + 触发层级/维度记录）；另新增只读值对象 `BudgetHeadroom`（frozen dataclass：`cost_remaining_ratio` + `tightest_scope`）与生产者 `headroom(session_id, user_id, agent_id)`（复用五层迭代算最紧层 cost 剩余比例，供 MR2 消费）。
  - 修改 `src/fleetent/config.py`：新增跨运行层预算上限与窗口 `Settings` 字段（上限默认 `NO_LIMIT` 向后兼容；窗口默认 `weekly`/`monthly`）。
  - 修改 `src/fleetent/agent_loop.py`：在既有 AR2 `BudgetChecker` 之外注册 `LayeredBudgetChecker`，并在主循环累计点把每轮用量写入 `BudgetStore`（复用 `BudgetUsage.add` 口径）；超限时经 `log_run` 写 `budget_scope`（触发层级）。具体接线在 design 钉死，本 change 不改 AR2 单运行预算语义。
- **配置**：新增 `agent_budget_*` 跨运行层上限字段（可选，缺省 `NO_LIMIT` 不拦截）与 `agent_budget_*_window` 窗口字段（缺省 weekly/monthly）。
- **测试**：新增 `tests/test_layered_budget.py`（层级枚举、配置默认、`BudgetStore` 累计/隔离、多层超限判定、触发层级/维度记录）；扩充 `tests/test_agent_loop.py` 断言层级检查器接线与跨运行累计；扩充 `tests/test_config.py` 断言新字段默认值。SQLite 隔离到 `tmp_path`，LLM 调用 mock。
- **不影响**：AR2 单运行预算 `budget.py`（仅引用不改）、termination 框架、context_mgr 压缩、permission_gate、im_gateway；不引入新依赖（`sqlite3` 标准库、AR2 已在用）。

## Dependencies

- **`src/fleetent/budget.py`（AR2，已实现）**：复用 `BudgetConfig`（`{max_turns, max_tokens, max_cost_usd}` + `NO_LIMIT` + `exhausted_dimension`）、`BudgetUsage`（`add(...)` 累计口径与单价换算）、`MODEL_PRICING`/`DEFAULT_PRICING`。本 change **不重造计量**。
- **`src/fleetent/termination.py`（AR1，已实现）**：`LayeredBudgetChecker` 实现 `TerminationChecker` 协议，超限返回预留的 `StopReason.budget_exceeded`，接入 `TerminationController`。
- **`docs/capabilities/wave2-apply-decisions.md`（AR2 应用决策）**：Grace Call 预算隔离已决（主预算固定比例默认 5%、保底 512）——本 change 复用既有 Grace Call 路径，不重定义比例/保底。
- **`src/fleetent/config.py`**：沿用 `Settings`（pydantic-settings，env-first）字段惯例承载五层默认上限。

## 被依赖（下游消费方）

- **`openspec/changes/cost-aware-routing`（MR2，成本感知路由）**：消费本 change 暴露的 `headroom()` + `BudgetHeadroom`（只读快照），获取当前最紧层 cost 剩余比例做路由决策。依赖方向单向 MR2→AR18（路由依赖预算）；类型与生产者均落本 change，MR2 仅 import 消费、不反向依赖。
