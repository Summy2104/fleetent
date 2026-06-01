## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 AR4 `loop_detector.arg_fingerprint(arguments, ignore_keys)` 签名与规范化语义（JSON sort_keys 哈希 / 非 JSON 回退 / `ignore_keys` 逃生舱），确认守卫直接复用该纯函数，不重造参数比较
- [ ] 1.2 核实 `termination.LoopState` 现有字段（`tool_history` / `loop_warning_injected`）与 `record_tool_call`；确认 AR10 新增的连续计数字段（如 `last_call_fingerprint` / `consecutive_repeat`）带默认值、对既有 AR4 checker 透明（向后兼容）
- [ ] 1.3 核实 `StopReason.loop_detected` 为既有预留枚举，守卫强制停止复用它、不新增枚举；核实 `_LOOP_WARNING_TEXT`（占位 tool_result 文案可复用或定制）；核实 termination-framework 给 `approval_rejected` 补占位 tool_result 的不变式（AR10 短路补占位同此）
- [ ] 1.4 确认守卫接入点（倾向 `agent_loop._safe_dispatch` 前，`dispatch` 保持纯工具执行收口，短路与占位 tool_result 注入落于此层）；确认未命中守卫时既有 dispatch 路径字节级不变
- [ ] 1.5 确认 `config.Settings` 现有 `agent_loop_repeat_threshold=3`，新增 `guardrail_repeat_threshold` 默认与之对齐；确认连续失败终止已由 AR1 `ConsecutiveFailuresChecker`（`agent_max_consecutive_failures`）覆盖，本 change 不新增失败阈值字段

## 2. 守卫阈值默认值与可配置（解决 Q3）

- [ ] 2.1 Write failing tests：`guardrail_repeat_threshold` 默认 3；阈值解析遵循「按次入参 > Settings > 默认」优先级；阈值经构造注入而非模块级全局可变量。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`config.Settings` 追加 `guardrail_repeat_threshold` 字段（默认 3）+ 守卫阈值解析（注入参数 None 回退 Settings），看到绿

## 3. 严格连续重复计数与触发（tool_guardrails.py）

- [ ] 3.1 Write failing tests：相同 `(tool, arg_fingerprint)` 背靠背连续达 N 次触发守卫；连续 2 次（N=3）不触发；中途夹入不同调用清零计数。`arg_fingerprint` 复用 `loop_detector`。看到红
- [ ] 3.2 Implement 严格连续重复计数器与触发判定（相同累加、相异清零，复用 `loop_detector.arg_fingerprint`），看到绿
- [ ] 3.3 Write failing test：参数语义相同但 JSON 键顺序不同时指纹相同、计入同一连续序列（与 AR4 判定一致）。看到红/绿确认复用指纹

## 4. 两阶段响应：首次短路+占位 tool_result，再次 loop_detected（tool_guardrails.py + agent_loop 接入）

- [ ] 4.1 Write failing tests：守卫首次命中**短路本次工具调用**（不执行）并为被跳过的 tool_call 补一条占位 tool_result（content 为纠正反馈文本），置共享 `loop_warning_injected`，本轮不返回终止；占位 tool_result 保消息序列合法（有 tool_call 必有对应 tool_result）。看到红
- [ ] 4.2 Implement 首次命中短路 + 占位 tool_result（content 复用 `_LOOP_WARNING_TEXT` 或定制文案）+ 置 `loop_warning_injected`；**不调用** `_maybe_inject_loop_warning`，看到绿
- [ ] 4.3 Write failing test：警告已注入后再命中返回 `StopReason.loop_detected`，不新增枚举。看到红
- [ ] 4.4 Implement 再次命中强制停止（复用 `loop_detected`），看到绿
- [ ] 4.5 Write failing test：守卫首次短路置 `loop_warning_injected` 后，AR4 轮间不重复注入第二条警告（共享幂等）；守卫不走 AR4 轮间注入通路。看到红
- [ ] 4.6 Implement 幂等共享与「不走 `_maybe_inject_loop_warning`」，看到绿

## 5. dispatch 边界接入与隔离（agent_loop）

- [ ] 5.1 Write failing test：守卫在 dispatch 调用前生效；未命中守卫时工具按既有逻辑 dispatch、结果与无守卫一致（既有用例不回归）。看到红/绿确认兼容
- [ ] 5.2 Implement 守卫接入点（`_safe_dispatch` 前调用守卫检查，命中则短路并补占位 tool_result），看到绿
- [ ] 5.3 Write failing test：连续计数随 per-run `LoopState` 隔离——独立 `LoopState` 的新运行从零起算，不受上次影响。看到红
- [ ] 5.4 Implement per-run 隔离（计数挂 `LoopState`，无全局可变状态），看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
