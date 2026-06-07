## Context

`runtime/context.py` 已有 `compress_for_context_overflow`（无条件压到 Tretained）与 `estimate_tokens`；`error_classifier` 已把 `context_length_exceeded` 归类 `context_overflow` 并标 `should_compress=True`/`should_switch_model=False`。但 `loop.py` 的 LLM 调用错误路径只 `_log_run_error` + `raise`（run）/ emit error（run_stream），**从不消费 `should_compress`**。

## Goals / Non-Goals

**Goals:** 接通"溢出→压缩→重试同 target"+ 守卫，覆盖 run 与 run_stream。

**Non-Goals:** 不做按模型 `context_window` 主动预算（暂缓）；不做工具结果 prune（暂缓）；不改 `compress_for_context_overflow` / `error_classifier` 既有语义。

## Decisions

### D1：反应式（而非主动预算）
反应式捕获真实 API 溢出错误后压缩重试——通用、无需为每个 model 配 `context_window`，对 on-prem 多后端最省心；主动预算需 per-model 窗口配置，价值被反应式覆盖后边际下降，暂缓。

### D2：`run()` 用 `_call_with_overflow_retry` 包装
新增 helper 包 `_call_policy_chat`：`except` 中 `classify(exc).should_compress and attempts < cap` 才压缩重试，否则 raise。原地 `messages[:] = compressed`（保持 caller 列表引用，session 持久化照旧）。

### D3：`run_stream()` 内联
溢出发生在 `await _stream_policy_chat`（流建立阶段，400）。在既有 `except (RateLimitError, APIStatusError)` 内加溢出分支：压缩 + `messages = compressed`（run_stream 本地 rebind）+ continue 重建流；恢复失败照旧 emit error 后 return。

### D4：守卫
`_MAX_OVERFLOW_COMPRESSIONS = 1`（溢出多为单次长输入，压一次到 Tretained 通常足够）；且 `estimate_tokens(compressed) >= before` → 放弃 re-raise（无进展守卫）。

## Risks / Trade-offs

- **[Risk] Tretained 仍 > 真实窗口** → 压缩后仍溢出：守卫在第二次（或无进展时）放弃，优雅 re-raise（仍优于现状直接崩溃）。彻底解决需 `context_window` 主动预算（暂缓项）。
- **[Risk] 流式已 emit 部分内容后溢出** → 不会：溢出在流建立阶段（首个 await）发生，尚未 emit 任何 chunk。
