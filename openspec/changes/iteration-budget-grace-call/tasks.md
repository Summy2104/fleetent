## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 AR1 框架接口：`termination.py` 的 `TerminationChecker` Protocol、`TerminationController.register` / `should_stop`、`StopReason.budget_exceeded` 与 `StopReason.max_turns` 已存在；核实 `MaxTurnsChecker` 在 `_build_controller`（行 46-59）的注册，确认其**退役**（不再注册）后由 `BudgetChecker` 承载步数维度（`StopReason.max_turns` 枚举成员保留，主循环不再产出，见 design D2）
- [ ] 1.2 核实主循环 token 用量来源：确认 `run()` 现状**仅在循环末取最后一次** `response.usage`（行 387）、循环内不累计，且 `run_stream()` 逐 chunk 累计 `total_prompt_tokens` / `total_completion_tokens`（行 525-527）；据此确认 D1 新增「每轮 LLM 调用返回后即 `usage.add(...)`」落点的插入位置（run / run_stream 两路径）
- [ ] 1.3 核实压缩调用落点：`maybe_compress`（agent_loop.py 行 299 / 492）内部 LLM 调用的 token 是否流经主循环 `response.usage` / 累计入口，确认 D4「压缩豁免在当前架构下默认成立（不流经 `BudgetUsage.add`，无需主动排除）」属实
- [ ] 1.4 核实 `log_run` 签名（eval_logger.py），确认新增末位 kw `budget_dimension: str | None = None` 向后兼容
- [ ] 1.5 核实 `config.Settings` 字段添加方式（config.py 行 7-25），确认新增预算上限 + Grace Call 比例/保底下限字段经 `.env` / `config/settings.yaml` 覆盖
- [ ] 1.6 核实模型可用名（`model_router.ROUTES` / cfg.model），据此定 `MODEL_PRICING` 单价表的 key；表外模型口径已在 design D5 定死为「保守默认单价 `DEFAULT_PRICING`，绝不计 0」，本步仅确认默认单价取值覆盖主流模型上限
- [ ] 1.7 核实 `run_stream()` 现状收尾结构：确认检查点命中后直接走 `log_run`（行 589）、**无**「break 后再发一次流式 LLM 并 `text_delta` 流出」结构，据此确认 D7 流式 Grace Call 收尾的插入点与降级分支落点

## 2. 预算配置、用量累计与成本估算（budget.py，对外契约）

- [ ] 2.1 Write failing tests：`tests/test_budget.py` 断言 `BudgetConfig` 含 `max_turns` / `max_tokens` / `max_cost_usd`（各支持「无上限」哨兵）；`BudgetUsage` 初始零用量。看到红
- [ ] 2.2 Implement `BudgetConfig`（frozen）与 `BudgetUsage`（可变累计器），看到绿
- [ ] 2.3 Write failing tests：`MODEL_PRICING` 静态表 + `BudgetUsage.add(prompt, completion, model)` 按单价换算累加成本、累加 token 与步数；表外模型按 D5 选定口径处理；单价表可 monkeypatch。看到红
- [ ] 2.4 Implement 单价表与 `add()` 换算，看到绿
- [ ] 2.5 Write failing tests：「将耗尽」判定——任一维度（turns / tokens / cost_usd）达上限即判定耗尽，并能报出触发维度；无上限维度不触发。看到红
- [ ] 2.6 Implement 三维判定（含触发维度），看到绿

## 3. BudgetChecker（接入 AR1 框架）

- [ ] 3.1 Write failing tests：`BudgetChecker(config, usage)` 在任一维度达上限时 `check()` 返回 `StopReason.budget_exceeded`，否则 None。看到红
- [ ] 3.2 Implement `BudgetChecker`，看到绿

## 4. Grace Call 预留预算计算

- [ ] 4.1 Write failing tests：`grace_max_tokens = max(round(max_tokens * ratio), floor)`；默认 ratio=0.05 / floor=512；主预算很小时取保底下限；ratio/floor 可配置覆盖。看到红
- [ ] 4.2 Implement Grace Call 预留计算（读 Settings 默认 + 可注入），看到绿

## 5. 主循环接入预算 + Grace Call（agent_loop.py）

- [ ] 5.1 Write failing tests for 逐轮计量与豁免：`run()` 在**每轮** LLM 调用返回后即把该轮 usage 累计进 `BudgetUsage`（步数 / token / 成本），而非循环末取一次（断言多轮后累计值 = 各轮之和，而非仅最后一轮）；压缩等系统内部调用产生的 token **不**进入 `BudgetUsage`（断言压缩不改变累计值）。mock `get_async_client_and_config`。看到红
- [ ] 5.2 Implement `run()` 每轮 LLM 调用返回后 `usage.add(...)`（D1 落点）+ `_build_controller` 退役 `MaxTurnsChecker`、注册 `BudgetChecker` + 压缩 token 不接入累计（D4 默认豁免），看到绿
- [ ] 5.3 Write failing tests for Grace Call 正常路径：预算将耗尽触发 `budget_exceeded` 时，发起一次额外 LLM 调用（带预留 token 上限 + 总结指令），其输出作为最终回复；`log_run(stop_reason=budget_exceeded, budget_dimension=...)`。看到红
- [ ] 5.4 Implement Grace Call 收尾（最后一次 LLM 调用 + trace 写入触发维度），看到绿
- [ ] 5.5 Write failing tests for Grace Call 失败降级：Grace Call 报错/超时/返回空 → 返回已有部分结果、记录降级、不崩溃、不重试。看到红
- [ ] 5.6 Implement 失败降级，看到绿
- [ ] 5.7 Write failing tests for `run_stream()` 逐轮计量与流式 Grace Call：每轮 LLM 调用结束时把该轮增量结算进 `BudgetUsage`（而非仅全流程末汇总）；预算命中后**发起一次流式 Grace Call**、总结经 `text_delta` 增量流出后 `done`（断言客户端收到总结增量，而非现状的「命中即直接收尾、无流式总结」）；预算命中不泄漏半截工具循环。看到红
- [ ] 5.8 Implement `run_stream()` 逐轮结算 + D7 流式 Grace Call 收尾结构（break 后再发一次流式 LLM、`text_delta` 流出总结、再 `done`），看到绿
- [ ] 5.9 Write failing tests for `run_stream()` 流式 Grace Call 降级：①Grace Call 尚未 yield 任何 `text_delta` 即失败 → 补发终止前已累积的最后一段文本后 `done`；②已 yield 部分 `text_delta` 后失败 → 以已流出内容收尾、`yield done`、记录降级，不回滚已流出增量、不重试、不抛未处理异常。看到红
- [ ] 5.10 Implement `run_stream()` 流式 Grace Call 的两类降级，看到绿

## 6. 配置项（config.py + settings.yaml.example）

- [ ] 6.1 Write failing test：`Settings` 含预算上限 + `agent_grace_call_token_ratio`（默认 0.05）+ `agent_grace_call_min_tokens`（默认 512），可被环境变量覆盖。看到红
- [ ] 6.2 Implement：`config.py` 新增字段；`config/settings.yaml.example` 补预算与 Grace Call 字段示例。看到绿

## 6b. max_turns 退役与既有用例迁移（可观察行为变更，proposal 迁移项）

- [ ] 6b.1 退役 `MaxTurnsChecker`：从 `_build_controller` 移除其注册（步数维度改由 `BudgetChecker` 承载）；保留 `StopReason.max_turns` 枚举成员，但确认主循环不再产出它。看到对应回归测试随之变化
- [ ] 6b.2 迁移 `tests/test_termination.py` 中针对 `MaxTurnsChecker` / `StopReason.max_turns` 的既有用例：改为断言步数维度命中由 `BudgetChecker` 产出 `StopReason.budget_exceeded`（触发维度为步数）；保留对 `StopReason.max_turns` 枚举成员存在性的断言（兼容性）
- [ ] 6b.3 迁移 `tests/test_agent_loop.py` 中断言 `stop_reason == "max_turns"` 或 max_turns 硬切断收尾的既有用例：改为断言 `budget_exceeded` + `budget_dimension == "turns"` + 经 Grace Call 收尾（非硬切断返回当时内容）
- [ ] 6b.4 全量跑 `uv run pytest -x -q`，确认无残留断言旧 `max_turns` 收尾语义的用例

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归（既有 `max_turns` 用例已按 6b 迁移到 `budget_exceeded` + Grace Call 收尾路径）
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 7.3 `uv run mypy src` 无新增错误模式
