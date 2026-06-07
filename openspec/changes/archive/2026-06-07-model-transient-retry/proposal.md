## Why

瞬时错误（429 rate_limit / mcp_disconnect）当前直接走"切模型 failover"。on-prem 单/少 provider 时 failover 无处可去 → 一次 429 就让整个 run 失败。`error_classifier` 早已为这些标了 `should_retry=True`，但**从未被用于"同 target 退避重试"**——只有切模型逻辑消费了 `should_switch_model`。

## What Changes

- **新增 `_create_with_transient_retry`**：对 `should_retry` 且非 `should_compress` 的瞬时错误，在**同一 target** 上退避重试——尊重 `Retry-After` 响应头，否则指数退避 + 抖动（capped），重试上限 `_MAX_TRANSIENT_RETRIES`。耗尽或非瞬时错误则抛出，由既有 failover 逻辑接管（429 仍 `should_switch_model=True`，退避耗尽后才切模型）。
- **接入** `_call_policy_chat` 与 `_stream_policy_chat` 的 create 调用。
- **排除 `context_overflow`**（`should_compress=True`）：它由 C3b 的溢出恢复处理，不在此做无效的同上下文重试。

## Capabilities

### New Capabilities

- `model-transient-retry`: 瞬时错误在同 target 上退避重试（尊重 Retry-After），先于切模型 failover。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（新增 `_create_with_transient_retry` / `_backoff_delay` / `_retry_after_seconds` + 两处 create 包装；`import random` 用于抖动）。
- **解耦合规**：纯 `runtime/`，无新依赖（random 为 stdlib）、无 platform。
- **暂缓（documented）**：把 5xx（500/502/503/504）归类为可重试需扩 `error_classifier` 的 category（当前 5xx 归 unknown 不重试）——后续单独小项；重试次数/基准延迟当前为模块常量，可后续做成 agent.yaml 可配。
