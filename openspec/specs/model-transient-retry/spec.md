# model-transient-retry Specification

## Purpose
TBD - created by archiving change model-transient-retry. Update Purpose after archive.
## Requirements
### Requirement: 瞬时错误在同 target 退避重试

当一次 LLM 调用因瞬时错误失败（`error_classifier` 判 `should_retry=True` 且 `should_compress=False`，如 429 rate_limit）时，agent loop SHALL 在**同一 target** 上退避重试，而非立即切模型或让 run 失败。退避 SHALL 尊重错误携带的 `Retry-After` 响应头（秒）；无该头时用指数退避 + 抖动，并受最大延迟上限约束。重试次数 MUST 受上限约束；上限耗尽后 MUST 抛出最后一次错误，交由既有 failover 逻辑处理（若该错误 `should_switch_model=True` 则切下一 target，否则向上传播）。`context_overflow`（`should_compress=True`）MUST NOT 在此重试（由上下文溢出恢复处理）。非瞬时错误（如鉴权失败）MUST 立即抛出、不重试。

#### Scenario: 瞬时错误退避后重试成功
- **WHEN** create 调用首次抛出 429（should_retry、非 should_compress），重试后成功
- **THEN** 同 target 退避重试并返回成功结果，run 不失败

#### Scenario: 重试上限耗尽后交给 failover
- **WHEN** 同 target 持续 429 至重试上限
- **THEN** 抛出最后一次错误；既有 failover 逻辑据 `should_switch_model` 切下一 target 或传播

#### Scenario: 上下文溢出不在此重试
- **WHEN** create 调用抛出 context_overflow（should_compress）
- **THEN** 不触发同 target 退避重试（交由溢出恢复），不在此循环重压

#### Scenario: 非瞬时错误立即传播
- **WHEN** create 调用抛出鉴权失败（should_retry=False）
- **THEN** 不重试，立即抛出

