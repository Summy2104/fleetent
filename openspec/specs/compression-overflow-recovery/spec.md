# compression-overflow-recovery Specification

## Purpose
TBD - created by archiving change compression-overflow-handling. Update Purpose after archive.
## Requirements
### Requirement: 上下文溢出时压缩并重试

当一次 LLM 调用因上下文过长（错误经 `error_classifier` 归类为 `context_overflow`、`should_compress=True`）失败时，agent loop SHALL 调用 `compress_for_context_overflow` 原地压缩当前消息序列并重试同一 target，而非直接让该次 run 崩溃。重试 MUST NOT 切换模型（`context_overflow` 的 `should_switch_model=False`）。非 `context_overflow` 的错误 MUST 保持既有行为（记录并向上传播）。阻塞 `run()` 与流式 `run_stream()` 两条路径均 SHALL 具备该恢复行为；流式路径在溢出发生于流建立阶段时恢复，恢复失败则照旧 emit error 事件后结束。

#### Scenario: 上下文溢出触发压缩重试后成功
- **WHEN** 首次 LLM 调用抛出 `context_length_exceeded`（归类 `context_overflow`），压缩后重试成功
- **THEN** 该 run 不崩溃，使用压缩后的消息序列继续，返回正常结果

#### Scenario: 非溢出错误保持既有传播
- **WHEN** LLM 调用抛出非 `context_overflow` 错误（如鉴权失败）
- **THEN** 不触发溢出压缩重试，错误按既有逻辑记录并传播

### Requirement: 压缩后守卫防止无限重压

上下文溢出恢复 MUST 受守卫约束：设重试次数上限；且当一次溢出压缩**未使估算 token 下降**（无进展）时 MUST 放弃并 re-raise，不得继续重压。守卫确保 un-shrinkable 的上下文不会陷入"压缩→仍溢出→再压缩"的死循环。

#### Scenario: 压缩无进展时放弃
- **WHEN** 溢出后压缩未使估算 token 下降
- **THEN** 恢复放弃并 re-raise 原错误，不再重试

#### Scenario: 超过重试上限后放弃
- **WHEN** 溢出压缩重试次数已达上限仍溢出
- **THEN** 恢复放弃并 re-raise，不无限重试

