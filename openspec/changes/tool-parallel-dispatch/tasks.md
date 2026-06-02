## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `run()` 主循环 tool_calls 段（agent_loop.py 行 ~739–843）：`for tc in msg.tool_calls` 内的 AR10 `evaluate_guardrail` 短路 / stop 分支、`_SUB_AGENT_TOOL` 特例（行 764）、`get_risk_level` + `_default_gate.request_approval` 审批分支、`_safe_dispatch` 调用、`consecutive_failures` 累计与 `record_tool_call`、tool 消息回填位置；据此确认 D1 三阶段（计划 / 执行 / 回填）的切分落点
- [ ] 1.2 核实 `run_stream()` tool_calls 段（行 ~1106–1160）：`tool_calls_list` 重建（行 1106–1114）、`tool_call` / `tool_result` 流式事件 yield 点、回填与计数；确认 D8 事件按原序产出的落点
- [ ] 1.3 核实 `_safe_dispatch`（行 293–331）已自带 T2 child token（行 314）+ `asyncio.wait_for` 硬停 + 异常 / 超时归一化为 `(text, failed=True)`；确认 AR3 并行只需 `gather` 这些已自带保护的调用、不传 `return_exceptions=True`
- [ ] 1.4 核实 run-level `token` 绑定（run() 行 661 / run_stream() 行 992）为并行批共享的 cancel token；确认取消传播复用既有 token、不新增 checker、不改 AR1 终止判定
- [ ] 1.5 核实 `SandboxManager.acquire`（sandbox_manager.py 行 95）对同一 session scope 返回同一 `ws_id`；确认 D5 同容器有状态工具（`run_code`）串行化的资源键与最小实现路径
- [ ] 1.6 核实 `SubAgentExecutor`（sub_agent.py）已 `asyncio.gather` 子任务 + 深度 1 守卫（行 764 `and not is_sub_agent`）；确认 D6 sub_agent 作为并行批中一个 awaitable 槽、深度约束不破
- [ ] 1.7 核实 `config.py` `Settings` 字段风格与加载（`.env` / `settings.yaml`、可 monkeypatch）；确认 D7 新增 `agent_tool_parallel_max` 的注入点

## 2. 并发上限配置（config.py）

- [ ] 2.1 Write failing test：`Settings.agent_tool_parallel_max` 默认 8；可经环境变量 / 注入覆盖；`<=1` 表示顺序退化（断言读取值）。看到红
- [ ] 2.2 Implement `Settings` 新增 `agent_tool_parallel_max: int = 8`，看到绿

## 3. N=1 等价现状（回归基线，最先锁定）

- [ ] 3.1 Write failing test for `run()` N=1：mock `get_async_client_and_config`，单 `tool_call` 一轮 → messages 回填内容 / 顺序、`consecutive_failures`、`record_tool_call` 与重构前字节级一致。看到红（重构未做时此测试应描述目标行为；以现状快照为基线断言）
- [ ] 3.2 Write failing test for `run_stream()` N=1：单 `tool_call` → `tool_call` / `tool_result` 事件序与 tool 消息回填与现状一致。看到红
- [ ] 3.3 Implement `run()` / `run_stream()` 的三阶段重构（计划 / 执行 / 回填），使 N=1 路径退化为等价现状，看到绿

## 4. N>1 并行执行 + 原序回填（D1/D2）

- [ ] 4.1 Write failing test for `run()` N>1：一轮多个独立工具 → 用可观察的并发证据（如 mock 工具记录进入时刻有重叠 / 用 `asyncio.Event` 编排断言并发）证明并行执行；tool 结果消息按原 `tool_calls` 索引顺序回填、`tool_call_id` 一一配对（即便 mock 让后位工具先完成）。看到红
- [ ] 4.2 Write failing test：回填序为原序而非完成序——构造后位工具先完成、前位后完成，断言 messages 仍按原序。看到红
- [ ] 4.3 Implement 阶段二 `asyncio.gather`（保序返回）+ 阶段三按原索引回填，看到绿
- [ ] 4.4 Write failing test：AR6 sanitize 不触发修复——N 个 tool_calls 后紧跟 N 条配对 tool 消息，序列合法。看到红
- [ ] 4.5 Implement 确保回填序列通过 sanitize 校验，看到绿

## 5. 并行批次取消传播（D1 + AR19 复用）

- [ ] 5.1 Write failing test：一批工具并行执行期 cancel token 取消 / deadline 命中 → 在途工具被中止（mock 工具观察 child token / 断言 `_safe_dispatch` 超时归一化）、主循环下一检查点以 `cancelled` 终止。看到红
- [ ] 5.2 Write failing test：取消时部分完成、部分在途 → 每个 `tool_call` 仍回填一条 tool 消息（结果或失败占位），无半截 tool-pair，sanitize 不报错。看到红
- [ ] 5.3 Implement 并行批共享 run-level token + 阶段三对每个原索引必回填（含取消占位），看到绿

## 6. 多风险工具审批策略（D3）

- [ ] 6.1 Write failing test：一轮多个 medium/high 工具 → `_default_gate.request_approval` 按原序串行逐个调用（断言调用顺序 / 非并发），全部批准后这些工具进入并行批执行。看到红
- [ ] 6.2 Write failing test：某高危工具被拒 → 不进并行批、回填拒批占位 + 置 `approval_rejected`，其余被批准工具仍并行执行。看到红
- [ ] 6.3 Implement 阶段一串行审批 + 阶段二仅对被批准工具 `gather`，看到绿

## 7. 失败隔离与逐结果计数（D4）

- [ ] 7.1 Write failing test：并行批中单工具失败（`_safe_dispatch` 归一化 failed）→ 同批其余正常返回、整批不中断；不使用 `return_exceptions=True` 掩盖（真异常应冒泡）。看到红
- [ ] 7.2 Write failing test：`consecutive_failures` 按原序逐结果更新（成功清零 / 失败加一），与顺序执行同等结果；`record_tool_call` 窗口记录按原序逐结果。看到红
- [ ] 7.3 Implement 阶段三逐结果更新计数与窗口记录，看到绿

## 8. 单轮并发上限分批（D7）

- [ ] 8.1 Write failing test：待执行工具数 > `agent_tool_parallel_max` → 分批并发（批间串行）、最终回填仍按原序；上限设为 1 → 全顺序执行等价现状。看到红
- [ ] 8.2 Implement 阶段二按上限分批 `gather`，看到绿

## 9. 共享沙箱容器并发边界（D5）

- [ ] 9.1 Write failing test：一轮多个作用于同一 session 沙箱容器的 `run_code` → 对该容器按资源键串行执行（mock 断言不并发同容器 exec）；不同容器 / 无共享状态工具仍并行。看到红
- [ ] 9.2 Implement 同容器有状态工具按资源键串行化（per 键 Lock 或同键收敛为顺序子协程），组间与其它工具并行，看到绿

## 10. run_stream 流式顺序（D8）

- [ ] 10.1 Write failing test for `run_stream()` N>1：`tool_call` 事件按原序、`tool_result` 事件在全批完成后按原序逐个产出（非完成序）；N 个 tool_call 对应 N 个 tool_result（含取消 / 失败占位），不泄漏半截事件。看到红
- [ ] 10.2 Implement `run_stream()` 并行期事件按原序产出，看到绿

## 11. sub_agent 嵌套不破（D6）

- [ ] 11.1 Write failing test：含 `sub_agent` 调用的一轮 → sub_agent 作为并行批中一个 awaitable 槽执行，其内部 `SubAgentExecutor` 仍自行 gather；子 agent（`is_sub_agent=True`）不再触发主循环 sub_agent 分支，深度 1 约束不破。看到红
- [ ] 11.2 Implement 将 sub_agent 纳入并行批为单一槽、保留深度守卫，看到绿

## 12. 收尾

- [ ] 12.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 12.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 12.3 `uv run mypy src` 无新增错误
