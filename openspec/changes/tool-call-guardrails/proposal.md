## Why

AR4 已实现的循环检测（`loop_detector.py`）是**主循环层粗粒度**地基：它注册为 `TerminationChecker`，在一轮工具全部 dispatch **之后**、下一次 LLM 调用前读取 `LoopState.tool_history` 滑动窗口，用两路信号（信号 A：`(tool_name, arg_fingerprint)` 在窗口内重复；信号 B：同工具成功结果 digest 停滞）判定「反复调用同一工具却毫无进展」，并两阶段响应（首次注入警告 → 仍重复则返回 `StopReason.loop_detected` 强制停止）。

`docs/capabilities/agent-runtime.md`（行 147-149）把**工具调用守卫（Guardrails，AR10）**列为比 AR4 更**细粒度**的能力：「相同工具 + 相同参数**连续**重复 N 次 → 注入警告；AI 忽略仍重复 → 停止调用」。AR4 的窗口计数无法表达「**严格连续**重复」这一更早、更精确的拦截点——窗口内 3 次（中间夹杂别的调用）与背靠背 3 次语义不同，后者是更确定的「卡死」信号，应在 dispatch 边界**调用前**就拦下，而不是等满一轮历史。

> **重定向注记（连续失败不归本 change）**：doc 行 149「同一工具**连续失败** M 次 → 同等处理」的连续失败终止**已由 AR1 `ConsecutiveFailuresChecker`（`agent_max_consecutive_failures=3`，任意工具连续失败 ≥3 → 停）覆盖**——失败只有在**执行后**才可知，「连续失败」天然是调用后检测，与 AR10「调用前边界」的身份矛盾；3 次同工具连续失败时 AR1 同样到 3 会先停，AR10 再设同工具失败计数器是重复。故本 change 的 AR10 **仅收窄为 N-重复守卫**，不含连续失败。如需「失败先警告后停」，属 AR1 `consecutive_failures` 策略增强，不在本 change。

`docs/capabilities/agent-runtime.md` 行 277 待决问题 Q3 一直悬空：「相同工具相同参数重复 N 次」中 N 默认值多少、是否可配置。本 change 必须给出明确决策（见 design.md「解决 Q3」），不留 OQ。

本 change 仅产出 spec 设计文档，不实现代码、不碰 `src/`。

## What Changes

- 新增**工具调用守卫**能力：在 `tool_registry.dispatch` 的**调用前边界**，对「相同工具 + 相同参数**严格连续**重复」做细粒度检测与拦截。
- 守卫**复用** AR4 的 `loop_detector.arg_fingerprint`（同一份参数指纹规范化逻辑，含 `ignore_arg_keys` 语义），**不重造**参数比较；与 AR4 共用 `StopReason.loop_detected` 终止原因。
- 守卫追踪**连续**计数（背靠背相同 → 累加，不同则清零），区别于 AR4 的**窗口**计数：AR4 看「最近 N 次里出现了几次」，AR10 看「连着出现了几次」。design.md 钉死二者分工，AR10 build on AR4 的指纹与终止词汇，不重复造循环地基。
- **解决 Q3**：N 默认值与可配置策略在 design.md 给明确决策（结论：N 默认 3，与 AR4 `agent_loop_repeat_threshold` 对齐；可配置，经 Settings 字段 + 按次注入参数覆盖，无全局可变状态）。
- 守卫命中时：①**首次（第 N 次连续、尚未警告）→ 短路本次调用**（不执行该工具，省掉冗余执行——这是 AR10 相对 AR4 的核心价值），为被跳过的 tool_call **补一条占位 tool_result**，其 content 即纠正反馈（兼作警告），并置共享 `loop_warning_injected` 幂等标志仅为与 AR4 协调；②已警告后再来一次相同调用 → 返回 `StopReason.loop_detected` 强制停止。AR10 **不走** AR4 的 `_maybe_inject_loop_warning`（轮间注入独立警告消息）通路——警告由这次的占位 tool_result 承载，不叠加轮间消息。

## Capabilities

### New Capabilities
- `tool-call-guardrails`: 工具调用守卫——在 dispatch 调用前边界检测「相同工具 + 相同参数严格连续重复 N 次」，复用 AR4 参数指纹与 `loop_detected` 终止词汇，首次命中短路本次调用并以纠正文本作占位 tool_result（保消息序列合法、兼作警告、置共享幂等标志），再次命中则返回 `loop_detected` 强制停止；N 默认 3、可经配置与按次注入覆盖。

### Modified Capabilities
<!-- 不修改既有 spec。AR4 循环检测已落在 agent-runtime 主 spec 的循环检测需求下，AR10 是其细粒度补充，作为新 capability `tool-call-guardrails` 以 ADDED 表达，build on（不替换、不修改）AR4 既有需求。 -->

## Impact

- **代码**（本 change 不实现，仅声明范围供后续实施）：
  - 新增守卫检测模块（建议 `src/fleetent/tool_guardrails.py`）：连续重复计数器 + 守卫判定，复用 `loop_detector.arg_fingerprint`。
  - 在 `tool_registry.dispatch` 调用边界或 `agent_loop._safe_dispatch` 前接入守卫检查；首次命中短路本次调用并以纠正文本补占位 tool_result（置共享 `loop_warning_injected` 幂等标志），再次命中返回 `StopReason.loop_detected`。
  - `config.Settings` 追加 `guardrail_repeat_threshold`（默认 3）字段。
- **配置**：新增一个可选阈值字段，缺省用默认值。
- **测试**：新增 `tests/test_tool_guardrails.py`（连续计数、清零、首次短路+占位 tool_result、再次 loop_detected、阈值注入、复用指纹）；LLM 调用 mock，路径隔离 tmp_path。
- **不影响**：AR4 `loop_detector` 的窗口检测逻辑（不改其语义，仅复用其指纹函数）；budget / consecutive_failures(AR1) / approval(AR3) 既有 checker 顺序；既有 `dispatch` 在未命中守卫时行为字节级不变。

## Dependencies

- `loop_detector`（AR4，已实现）：复用 `arg_fingerprint`（参数指纹规范化 + `ignore_arg_keys`）；AR10 build on，不重造循环检测地基。注意 AR10 **不复用** AR4 的 `_maybe_inject_loop_warning` 轮间注入通路——AR10 是 per-call、警告由占位 tool_result 承载，仅与 AR4 共享 `loop_warning_injected` 幂等标志以协调。
- `termination`（已实现）：复用 `StopReason.loop_detected` 终止原因、`LoopState`（`tool_history` / `loop_warning_injected`）承载守卫状态。补占位 tool_result 与 termination-framework 给 `approval_rejected` 补占位遵循同一不变式（有 tool_call 必有对应 tool_result）。
- `tool_registry`（已实现）：守卫在 `dispatch` 调用前边界接入；`agent_loop` 现有 `_safe_dispatch` 为短路与占位 tool_result 注入点。
