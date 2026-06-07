## Context

`run()`（loop.py ~1514）与 `run_stream()`（~1917）在 `finish_reason != "tool_calls"` 时 `break` 返回最终回复。弱模型偶发空回复 → 返回 `""`。

## Goals / Non-Goals

**Goals:** 空回复时注入纠正并重跑（带上限），覆盖 run + run_stream。

**Non-Goals（暂缓）:** planning-only（非空但无行动）的语义检测（模糊、误纠风险）；可配重试上限（当前常量）。

## Decisions

### D1：仅对空白回复纠正，带本地计数上限
finish 分支判断 `reply.strip()` 为空且本路重试计数 < `_MAX_EMPTY_REPLY_RETRIES` → 追加纠正 `user` 消息 + `continue`（重入 while，过终止检查），否则 `break`。计数为各自函数的本地变量（不污染 LoopState）。截断（`finish=length`）等非空回复不纠正。

### D2：注入点与序列合法性
纠正消息在 finish 分支追加（此时 assistant 空消息已 append）。`[..., assistant(空), user(纠正)]` 对 LLM 合法；下一轮 compress/sanitize 照常处理。

## Risks / Trade-offs

- **[Risk] 与预算/终止交互**：重跑即新一轮，受 budget/turns 终止与 `_MAX_EMPTY_REPLY_RETRIES` 双重约束，不会无限。
- **[Trade-off] 不处理 planning-only**：空回复是明确信号；"光说不做"的判定留后续，避免误纠正正常的纯文本回答。
