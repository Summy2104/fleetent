## Why

撞模型上下文上限（`context_length_exceeded`）时，loop 当前仅 `_log_run_error` 后 `raise`，整个 run 崩溃。`compress_for_context_overflow`（context.py）与 `error_classifier` 的 `context_overflow → should_compress=True` 骨架早已存在，但**从未被消费**——catch→compress→retry 的编排完全没接线。

## What Changes

- **反应式溢出恢复**：`run()` 与 `run_stream()` 的 LLM 调用在 `context_overflow` 错误时，消费 `classify(exc).should_compress` → 调 `compress_for_context_overflow` 原地压缩 `messages` → 重试**同一 target**（context_overflow 的 `should_switch_model=False`，不切模型）。
- **压缩后守卫**：重试上限（`_MAX_OVERFLOW_COMPRESSIONS`）+「压缩无进展（token 未下降）即放弃并 re-raise」，防止 un-shrinkable 上下文无限重压。

## Capabilities

### New Capabilities

- `compression-overflow-recovery`: loop 在上下文溢出错误时压缩并重试、带守卫的恢复行为。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（新增 `_call_with_overflow_retry` 供 `run()`；`run_stream()` 内联溢出重试；从 `runtime.context` 增 import `compress_for_context_overflow` / `estimate_tokens`）。
- **解耦合规**：纯 `runtime/`，复用既有 `compress_for_context_overflow`，无新依赖、无 platform、无新配置。
- **范围说明（C3b 实施期聚焦）**：本 change 是 C3b 的核心（反应式恢复 + 守卫）。原 C3b 计划中的「按模型 `context_window` 主动预算」与「工具结果 prune」**暂缓**为后续小项——反应式恢复已通用地防住崩溃（无需 per-model 配 `context_window`，对 on-prem 多后端更省心），prune 是独立的 token 回收优化。
