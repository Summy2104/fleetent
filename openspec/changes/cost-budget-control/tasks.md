## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `src/fleetent/budget.py`（AR2）对外契约：`BudgetConfig`（`max_turns/max_tokens/max_cost_usd` + `NO_LIMIT` + `exhausted_dimension(usage)`）、`BudgetUsage.add(prompt, completion, model)` 累计口径与单价换算（`MODEL_PRICING`/`DEFAULT_PRICING`）——确认本 change 复用、不重造计量
- [ ] 1.2 核实 `src/fleetent/termination.py`（AR1）：`TerminationChecker` 协议（`check(state) -> StopReason | None`）、`StopReason.budget_exceeded` 已预留、`TerminationController.register/should_stop`（返回首个非 None）
- [ ] 1.3 核实 `agent_loop.py` 现有 AR2 接线点：`_build_controller` 注册 `BudgetChecker`、主循环 `_budget_add(usage, response.usage, model)` 累计落点、`budget_exceeded` → Grace Call 收尾路径（复用，不重写）
- [ ] 1.4 核实 `config.py` `Settings` 字段惯例（`agent_max_*` 命名、env-first、默认 `NO_LIMIT` 向后兼容）；核实 `data/users.db` 既有表与 monkeypatch `DB_PATH` 隔离惯例（标准库 `sqlite3`，不用 aiosqlite）

## 2. 五层枚举与每层上限配置（layered_budget.py）

- [ ] 2.1 Write failing tests：`BudgetScope` 枚举含 `task`/`session`/`user`/`agent`/`global` 五值；检查顺序常量为由窄到宽。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `BudgetScope(StrEnum)` 与层级顺序常量，看到绿
- [ ] 2.3 Write failing tests：`LayeredBudgetConfig` 未配置层等价 `BudgetConfig(NO_LIMIT, NO_LIMIT, NO_LIMIT)`；`from_settings` 仅覆盖配置了的层/维度、其余回退 `NO_LIMIT`。看到红
- [ ] 2.4 Implement `LayeredBudgetConfig`（`per_scope: dict[BudgetScope, BudgetConfig]` + `from_settings`，复用 AR2 `BudgetConfig`），看到绿

## 3. 跨运行累计存储（layered_budget.py / BudgetStore）

- [ ] 3.1 Write failing tests：`BudgetStore.add(scope, key, prompt, completion, model, now=...)` 后 `get(scope, key, now=...)` 返回累计 `BudgetUsage`；增量换算与 AR2 `BudgetUsage().add(...)` 一致（同输入同结果）。`monkeypatch DB_PATH` 到 tmp_path。看到红
- [ ] 3.2 Implement `BudgetStore`（模块级 `DB_PATH` 可注入；建表 `budget_usage(scope,key,period,turns,tokens,cost_usd, PK(scope,key,period))`；`add` 委托 `BudgetUsage().add` 算增量、由 `now`+该层窗口算 `period` 后 `INSERT ... ON CONFLICT(scope,key,period) DO UPDATE` 原子累加；`get` 按 `now` 算当前 `period` 读回包成 `BudgetUsage`，无行返回全 0），看到绿
- [ ] 3.3 Write failing tests：同一 `(scope,key,period)` 多次 `add` 单调累加；不同 key 互不串扰；`global` 哨兵 key 独立于任意 user/agent 键。看到红
- [ ] 3.4 Implement 累计隔离逻辑（哨兵 key 常量 + 主键隔离），看到绿
- [ ] 3.5 Write failing test：`task` 层不作为跨运行层写入 `BudgetStore`（仅 session/user/agent/global 落盘）。看到红
- [ ] 3.6 Implement：`BudgetStore` 仅接受四个可落盘层、对 `task` 拒绝或不持久化，看到绿
- [ ] 3.7 Write failing tests：`period` 由可注入时钟（UTC `now`）按窗口计算——`lifetime`→`"lifetime"`、`daily`→`"YYYY-MM-DD"`、`weekly`→ISO `"YYYY-Www"`、`monthly`→`"YYYY-MM"`；用固定 `now` 断言各窗口 period 串。看到红
- [ ] 3.8 Implement `BudgetWindow`（`{lifetime,daily,weekly,monthly}`）与 `period` 计算（可注入时钟，UTC，`weekly` 用 `now.isocalendar()`），看到绿
- [ ] 3.9 Write failing tests：跨周期翻滚——用注入时钟在某周期 `add` 后，把 `now` 推到下一周期再 `get`，新周期累计从 0 起、落入新行；`lifetime` 窗口跨多个日历周期 `period` 恒为 `"lifetime"`、累计持续叠加。看到红
- [ ] 3.10 Implement：确认 `period` 入主键使跨周期 `add`/`get` 自然落新行（涌现式重置，无定时清零），看到绿
- [ ] 3.11 Write failing tests：各层默认窗口 `session`→`lifetime` / `user`→`weekly` / `agent`→`weekly` / `global`→`monthly`，store 按该层默认窗口算 period。看到红
- [ ] 3.12 Implement 各层默认窗口映射，看到绿

## 4. 跨运行层聚合检查器（layered_budget.py / LayeredBudgetChecker）

- [ ] 4.1 Write failing tests：`LayeredBudgetChecker.check` **只迭代 4 个跨运行层**（session/user/agent/global，不含 task）按由窄到宽对每层取 `store.get(scope,key,now=clock())` 调 `BudgetConfig.exhausted_dimension`；某层超限返回 `StopReason.budget_exceeded` 并记 `triggered_scope`/`triggered_dimension`；各层未超返回 None。看到红
- [ ] 4.2 Implement `LayeredBudgetChecker`（实现 `TerminationChecker`，可注入 `clock`，复用 AR2 `exhausted_dimension`，记录触发层级+维度），看到绿
- [ ] 4.3 Write failing test：多层同超时报最窄层（如 user 与 global 同超 → 报 user）。看到红
- [ ] 4.4 Implement 由窄到宽顺序保证，看到绿
- [ ] 4.5 Write failing test：某层 `key` 缺失（如无 session_id/user_id 的纯 CLI 运行）时跳过该层检查，不归入空 key、不混桶；仅对有 key 的层判定。看到红
- [ ] 4.6 Implement key 缺失跳过逻辑，看到绿

## 5. Settings 跨运行层上限与窗口字段（config.py）

- [ ] 5.1 Write failing tests：`Settings` 新增跨运行层 `agent_budget_{session,user,agent,global}_{dim}` 上限字段（默认 `NO_LIMIT`，-1 / -1.0），**不含 `agent_budget_task_*`**（task 归 AR2）。看到红
- [ ] 5.2 Implement 新增跨运行层上限 `Settings` 字段（默认 `NO_LIMIT`，env-first，沿用 `agent_max_*` 惯例），看到绿
- [ ] 5.3 Write failing tests：`Settings` 新增窗口字段 `agent_budget_{user,agent,global}_window`（默认 `user`/`agent`→`weekly`、`global`→`monthly`），session 固定 `lifetime` 无对应字段。看到红
- [ ] 5.4 Implement 窗口字段（默认值如上，取值校验为 `BudgetWindow` 之一），看到绿

## 6. agent_loop 接线（与 AR2 BudgetChecker 并存）

- [ ] 6.1 Write failing test：`LayeredBudgetChecker` 与 AR2 `BudgetChecker` 同注册到 `TerminationController`；主循环累计落点对 session/user/agent/global 各调一次 `store.add(...，now=clock())`（复用 `BudgetUsage.add` 口径）。LLM 调用 mock、SQLite 隔离 tmp_path。看到红
- [ ] 6.2 Implement：在既有 AR2 接线旁注册 `LayeredBudgetChecker`（注入 clock）并写入 `BudgetStore`，看到绿
- [ ] 6.3 Write failing test：压缩调用消耗的 token 不计入任何层级累计（豁免）。看到红/绿确认豁免（沿用 AR2「不接入即豁免」）
- [ ] 6.4 Write failing test：层级超限走 AR2 既有 `budget_exceeded` → Grace Call 收尾、不硬切断；`log_run` 写入可选字段 `budget_scope`（触发层级）。看到红
- [ ] 6.5 Implement：超限时经 `log_run` 传 `budget_scope`（沿用波次2 `disabled_skills_trace` 加可选字段范式），看到绿

## 7. headroom 只读快照（layered_budget.py）

- [ ] 7.1 Write failing tests：`BudgetHeadroom`（frozen dataclass）含 `cost_remaining_ratio: float`（∈[0,1]）与 `tightest_scope: str | None`；为只读（frozen，赋值抛错）。看到红
- [ ] 7.2 Implement `BudgetHeadroom` 数据类，看到绿
- [ ] 7.3 Write failing tests：`headroom(session_id, user_id, agent_id)` 复用五层迭代——某层 `cost_usd` 接近上限时 `cost_remaining_ratio = (上限-累计)/上限` 为该最紧层的较小比例、`tightest_scope` 为该层名；多层有 cost 上限时取最小剩余比例的层。`monkeypatch DB_PATH` 到 tmp_path、注入固定 clock。看到红
- [ ] 7.4 Implement `headroom()`（复用与 `LayeredBudgetChecker` 同一套 session/user/agent/global 层迭代 + `BudgetStore.get` 读累计 + `LayeredBudgetConfig` 上限对照，对配了 `cost_usd` 上限的层算剩余比例取最小者），看到绿
- [ ] 7.5 Write failing tests：无任何层配 `cost_usd` 上限时 `cost_remaining_ratio=1.0`、`tightest_scope=None`。看到红
- [ ] 7.6 Implement 无 cost 上限=充裕(1.0/None) 分支，看到绿
- [ ] 7.7 Write failing tests：某层 `key` 缺失（纯 CLI 无 session_id/user_id）时跳过该层、不参与剩余计算（沿用 key 缺失跳过）。看到红
- [ ] 7.8 Implement key 缺失跳过逻辑（复用聚合检查器同一跳过语义），看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 8.3 `uv run mypy src` 无新增错误
