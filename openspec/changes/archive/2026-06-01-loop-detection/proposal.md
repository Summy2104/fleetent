## Why

主循环（`agent_loop.run()` / `run_stream()`）当前没有任何手段识别 AI 陷入「反复调用同一工具却毫无进展」的状态：只要 LLM 持续返回 `tool_calls`，循环就一直转，直到撞上 `max_turns` 或 `consecutive_failures` 才停。但「同一工具被反复调用、结果毫无变化」并不等于失败（工具每次都成功返回），`consecutive_failures` 不会计数；于是 AI 可能空转十几轮、烧掉预算，最终才被 `max_turns` 兜底——既浪费成本，又让用户长时间得不到有效回复。

这是 AR4（循环检测）。它在主循环层做**粗粒度**检测：观察工具调用序列，识别「同一工具 + 相同/相似调用反复出现而无进展」的模式。AR1 终止框架（已合入 `termination.py`）已预留 `loop_detected` 原因码与「checker 注册即接入、不改循环体」的扩展点，本 change 正是为该原因码补上对应的 checker。

> 细粒度的「相同工具 + 相同参数连续重复 N 次」工具调用守卫（Guardrails）是 AR10（波次 3），不在本 change 范围；本 change 只做主循环层的粗粒度检测。

## What Changes

- 新增**循环检测 checker**（建议 `src/fleetent/loop_detector.py`）：作为一个 `TerminationChecker` 注册到 `TerminationController`，复用 AR1 已预留的 `loop_detected` 原因码，**不改主循环热点**。
- checker 观察主循环维护的工具调用历史（工具名 + 归一化后的参数指纹），识别「同一工具调用反复出现且无进展」的粗粒度循环模式。
- 采用**两段式响应**：首次检测到疑似循环 → 不立即终止，而是向消息序列注入一条警告提示（提醒 AI「正在重复同一操作、似乎没有进展，请换一种方式或直接给出结论」）；若 AI 忽略警告、仍继续重复 → checker 第二次命中即以 `loop_detected` 原因码强制终止。
- 在 `LoopState` 中扩展承载工具调用历史与「警告是否已注入」的轻量状态，由主循环每轮更新、checker 只读判定，沿用 AR1 的「标志位/状态驱动循环」模式。
- 检测阈值（重复多少次算循环、相似度判据）可通过参数注入 / 配置覆盖默认值；`loop_detected` 终止时原因码写入 trace（复用 AR1 的 `stop_reason` 出口）。

## Capabilities

### New Capabilities
- `agent-loop-detection`: 主循环层粗粒度循环检测——识别「同一工具反复调用却无进展」，先注入警告提示给 AI 自救，AI 忽略仍重复则以 `loop_detected` 原因码强制终止。实现为注册进 AR1 终止框架的独立 checker，阈值可配置，不修改主循环判定分支。本 capability 同时新增一条「`loop_detected` 终止已接入主循环」需求：AR1 spec 把 `loop_detected` 列为「已定义但无 checker、永不触发」的预留原因码，本 change 注册对应 checker 后该原因码成为可触发终止原因——该接入需求归本 change 自己的新 capability（ADDED），不 MODIFY `agent-loop-termination`，避免与并行 change（取消传播 / 迭代预算）就同一条注册表需求互相覆盖。

### Modified Capabilities
<!-- 无。不 MODIFY agent-loop-termination：AR1 spec「预留原因码尚未激活」的表述由本 change 自带的「loop_detected 终止已接入主循环」ADDED 需求超越；与并行 change 各自 ADD、互不冲突。归档顺序见 design ## Context。 -->


## Impact

- **代码**：
  - 新增 `src/fleetent/loop_detector.py`（参数归一化/指纹函数 + `LoopDetectionChecker` + 两段式状态判定）。
  - 修改 `src/fleetent/termination.py`：在 `LoopState` 上扩展工具调用历史与「警告已注入」标志（默认空，向后兼容）；`loop_detected` 原因码已存在，无需新增枚举。
  - 修改 `src/fleetent/agent_loop.py`：`_build_controller` 注册 `LoopDetectionChecker`；主循环在每次工具调用后把（工具名 + 参数指纹）记入 `LoopState`；当 checker 请求注入警告时，向 `messages` 追加一条警告提示消息（不发起额外 LLM 调用，仅在下一轮生效）。`run()` 与 `run_stream()` 两路径均接入。
- **配置**：新增 Settings 字段 `agent_loop_repeat_threshold`（默认值见 design D3），可经 `.env` / `config/settings.yaml` 覆盖。检测窗口大小与警告消息角色不暴露为配置，在 propose 阶段定死（见 design D3 / D4），避免可观察阈值语义随部署漂移。
- **测试**：新增 `tests/test_loop_detector.py`（指纹归一化、两段式判定、阈值）；`tests/test_agent_loop.py` 补充「反复同工具调用 → 先注入警告 → 仍重复 → `loop_detected` 终止」用例；`tests/test_termination.py` 补充 `LoopState` 历史字段。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：model fallback、错误分类（AR5）、工具 dispatch、permission_gate、上下文压缩的既有行为；`max_turns` / `consecutive_failures` / `approval_rejected` 判定不变；不引入新依赖。
