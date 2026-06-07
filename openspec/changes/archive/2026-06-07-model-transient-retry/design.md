## Context

`_call_policy_chat` / `_stream_policy_chat` 遍历 fallback candidates；某 target 失败时，`should_switch_model` 决定切下一 target，否则 raise。`error_classifier` 的 `should_retry`（rate_limit/mcp_disconnect/context_overflow=True）**从未被消费**于"同 target 重试"。on-prem 单 target 时，429 直接 raise。

## Goals / Non-Goals

**Goals:** 同 target 退避重试瞬时错误（尊重 Retry-After），先于 failover；覆盖阻塞 + 流式两路。

**Non-Goals（暂缓）:** 把 5xx 归类为可重试（需扩 error_classifier category）；重试参数 agent.yaml 可配（当前常量）；修改 failover/熔断语义。

## Decisions

### D1：`_create_with_transient_retry(do_call)` 包装 create
helper 接收无参 awaitable 工厂，循环：成功即返回；`except` 中 `should_retry and not should_compress and attempt < cap` → 退避后重试，否则 raise。两处 create 各传一个 `lambda` 工厂。raise 后由既有 except 决定 failover/传播——与现状兼容。

### D2：退避 = Retry-After 优先，否则指数+抖动
`_retry_after_seconds(exc)` 解析 `exc.response.headers["retry-after"]`（数值秒；HTTP-date 形式不解析→回退指数）。否则 `min(base*2^attempt, cap)` 半抖动。`_backoff_delay` 可在测试中 patch 为 0 以免真实等待。

### D3：排除 context_overflow
`should_compress` 的错误不在此重试（同上下文重试无意义、且 C3b 的 `_call_with_overflow_retry` 负责压缩+重试）。

## Risks / Trade-offs

- **[Risk] 重试放大下游压力** → cap + 尊重 Retry-After + 抖动；429 的 should_switch_model 仍在耗尽后切模型。
- **[Trade-off] 5xx 暂不重试** → 当前 5xx 归 unknown；扩 error_classifier 留作后续，避免本 change 触及分类表 + 其 spec。
