## Why

on-prem 常用的开源弱模型有时返回**空的最终回复**（`finish_reason=stop`、content 为空/纯空白、无工具调用），当前 loop 直接返回 `""`——用户收到空消息、任务实际未完成。

## What Changes

- **空回复自纠错**：`run()` 与 `run_stream()` 在 `finish_reason != "tool_calls"` 且最终回复为空白时，注入一条纠正性 `user` 消息（"上一条回复为空，请直接给出答案或调用合适工具继续"）并**重跑**，受上限 `_MAX_EMPTY_REPLY_RETRIES` 约束；回复非空或达上限则照常返回（达上限仍返回当前的 `""`，不无限重试）。

## Capabilities

### New Capabilities

- `agent-empty-reply-correction`: 模型返回空最终回复时注入纠正并重跑（带上限）。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（`run()` 与 `run_stream()` 的 finish 分支 + 每路一个本地重试计数）。
- **解耦合规**：纯 `runtime/`，无新依赖、无 platform；非空回复零行为变化。
- **暂缓（documented）**：planning-only（非空但"光说不做/无行动"）的语义检测——判定"本应行动却未行动"较模糊、误纠风险高，留作后续；空回复是清晰可测的信号，先做这一刀。
