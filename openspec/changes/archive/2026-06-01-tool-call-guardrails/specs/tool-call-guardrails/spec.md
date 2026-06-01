## ADDED Requirements

### Requirement: 相同工具相同参数严格连续重复触发守卫

工具调用守卫 SHALL 在 dispatch 调用前边界检测「相同工具 + 相同参数**严格连续**重复」。当同一 `(tool_name, 参数指纹)` **背靠背连续**出现达到阈值 N 次时 MUST 触发守卫。参数是否「相同」MUST 复用 AR4 `loop_detector.arg_fingerprint` 的规范化判定（含 `ignore_arg_keys` 语义），不另立比较标准。两次相同调用之间夹入任何不同调用时，连续计数 MUST 清零重计。

> 归属说明：本能力是 AR4 主循环层粗粒度循环检测的**细粒度补充**，落在新 capability `tool-call-guardrails` 下以 ADDED 表达，build on AR4 既有循环检测需求（不替换、不修改）。AR4 用窗口计数 / 调用后判定 / 终止 checker；本能力用严格连续计数 / 调用前判定 / dispatch 边界守卫。

#### Scenario: 连续重复达 N 次触发守卫
- **WHEN** 同一工具以相同参数（指纹相同）背靠背连续调用达到阈值 N（默认 3）次
- **THEN** 守卫被触发，进入两阶段响应（首次短路本次并补占位 tool_result，随后再命中强制停止）

#### Scenario: 连续 2 次不触发（避免误杀）
- **WHEN** 同一工具以相同参数连续调用 2 次（默认 N=3 未达）
- **THEN** 守卫不触发，调用照常执行

#### Scenario: 中途夹入不同调用清零计数
- **WHEN** 同一工具相同参数调用 2 次后，夹入一次不同工具或不同参数的调用，再调用原相同参数 1 次
- **THEN** 连续计数已清零，原相同参数仅记为新一轮的第 1 次，守卫不触发

#### Scenario: 复用 AR4 参数指纹判定相同
- **WHEN** 两次调用参数语义相同但 JSON 键顺序不同
- **THEN** 二者经 `arg_fingerprint` 规范化后指纹相同，计入同一连续重复序列（与 AR4 判定一致）

### Requirement: 守卫命中先短路后停止两阶段响应

守卫命中时 SHALL 采用两阶段响应。**首次命中**（第 N 次连续、尚未警告）MUST **短路本次工具调用**（不执行该工具），并为被跳过的 tool_call **补一条占位 tool_result**，其 content MUST 为纠正反馈文本——该占位 tool_result 同时保证消息序列合法（有 tool_call 必有对应 tool_result，与 termination-framework 给 `approval_rejected` 补占位同一不变式）并作为给 LLM 的警告。首次命中 MUST 置共享 `loop_warning_injected` 幂等标志（仅为与 AR4 协调，避免 AR4 再注入第二条轮间警告）。守卫 MUST NOT 走 AR4 的轮间警告注入通路（`_maybe_inject_loop_warning`）——警告由本次占位 tool_result 承载，不叠加轮间独立消息。**警告已注入后守卫再次命中**（又来一次相同调用），MUST 返回 `StopReason.loop_detected` 强制停止。守卫 MUST NOT 新增终止原因枚举，复用既有 `loop_detected`。

#### Scenario: 首次命中短路本次并补占位 tool_result
- **WHEN** 守卫首次命中（连续重复达 N）且尚未注入过循环警告
- **THEN** 短路本次工具调用（不执行该工具），为被跳过的 tool_call 补一条占位 tool_result，其 content 为纠正反馈文本，并置 `loop_warning_injected`；本轮不返回终止原因

#### Scenario: 占位 tool_result 保消息序列合法
- **WHEN** 守卫短路某次 tool_call
- **THEN** 该 tool_call 仍有对应的占位 tool_result，消息序列不出现「有 tool_call 而无 tool_result」的非法状态

#### Scenario: 警告后再命中强制停止
- **WHEN** 警告已注入（`loop_warning_injected` 为真）后守卫再次命中
- **THEN** 返回 `StopReason.loop_detected`，主循环强制停止

#### Scenario: 不走 AR4 轮间注入且与 AR4 共享幂等
- **WHEN** 守卫首次命中短路并置 `loop_warning_injected` 后，AR4 窗口检测在轮间评估是否注入警告
- **THEN** AR4 不重复注入第二条轮间警告（共享 `loop_warning_injected` 幂等标志），守卫自身亦不调用 `_maybe_inject_loop_warning`

### Requirement: 守卫阈值默认值与可配置

守卫的连续重复阈值 N SHALL 默认为 3（与 AR4 `agent_loop_repeat_threshold` 默认对齐）。N MUST 可配置，经 `config.Settings.guardrail_repeat_threshold` 字段（部署级）与按次注入参数（call 级）覆盖，遵循「按次入参 > Settings > 默认」优先级。阈值 MUST NOT 以模块级可变全局状态承载；默认值 MUST 有单一事实来源（Settings 字段 / 函数签名）。

> 归属说明：连续失败阈值不在本能力——连续失败终止已由 AR1 `ConsecutiveFailuresChecker`（`agent_max_consecutive_failures=3`）覆盖，本能力不引入 `guardrail_consecutive_failure_threshold`。

#### Scenario: 未配置时使用默认阈值
- **WHEN** 未声明任何守卫阈值配置
- **THEN** N 取默认值 3

#### Scenario: 按次注入阈值覆盖默认
- **WHEN** 调用方按次注入 `guardrail_repeat_threshold=2`
- **THEN** 本次运行连续重复阈值为 2（连续 2 次相同即触发），不影响其他运行

#### Scenario: Settings 配置覆盖默认
- **WHEN** `config.Settings` 声明 `guardrail_repeat_threshold=5` 且按次未注入
- **THEN** 连续重复阈值取 5

### Requirement: 未命中守卫时不改变既有 dispatch 行为

守卫在 dispatch 调用前边界生效，未命中守卫（绝大多数调用）时 MUST NOT 改变既有工具 dispatch 的行为与结果，不引入额外对外副作用。守卫连续计数 SHALL 随 per-run `LoopState` 生命周期，运行结束即消亡，MUST 实现 per-run 隔离，不在运行间泄漏状态。

#### Scenario: 未命中守卫调用照常
- **WHEN** 工具调用未达任何守卫阈值
- **THEN** 该工具按既有逻辑正常 dispatch，结果与无守卫时一致

#### Scenario: 计数 per-run 隔离
- **WHEN** 一次运行的连续计数已累加后，另一次运行（独立 `LoopState`）开始
- **THEN** 新运行的连续计数从零起算，不受上一次运行影响
