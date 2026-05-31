## ADDED Requirements

### Requirement: Injected context trace public API
系统 SHALL 提供 `InjectedContextTrace` 和 `record_injected_context(run_id, sources, ...)`
public API，用于记录最终注入 prompt 的长期上下文来源摘要。

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `InjectedContextTrace` 和 `record_injected_context`
- **THEN** 导入成功

#### Scenario: Injected context source shape
- **WHEN** 调用方构造 `InjectedContextTrace`
- **THEN** 该对象包含 source_id、source_type、score、token_estimate 和 metadata

#### Scenario: Unknown token estimate is explicit
- **WHEN** 单个 source 的 token estimate 暂不可得
- **THEN** 调用方可以设置 `token_estimate=0`
- **AND** payload 中仍包含 token_estimate 字段

### Requirement: Injected context trace event
`record_injected_context()` SHALL 将来源摘要写为 `event_type="injected_context"` 的 trace event。

#### Scenario: Record injected context event
- **WHEN** 调用 `record_injected_context(run_id="run-1", sources=[source])`
- **THEN** `traces` 表中出现 run_id=`run-1` 且 event_type=`injected_context` 的事件

#### Scenario: Sources are persisted as summary
- **WHEN** injected_context event 被写入
- **THEN** payload 包含 sources summary
- **AND** 每个 source summary 包含 source_id、source_type、score、token_estimate 和 metadata

### Requirement: Source attribution content safety
系统 SHALL 默认只保存来源摘要，不保存完整 memory、knowledge content 或完整对话 transcript。

#### Scenario: Raw content is not persisted
- **WHEN** `record_injected_context()` 写入 sources
- **THEN** payload 中不包含 `content`、`text` 或 `transcript` 字段

#### Scenario: Sensitive metadata is redacted
- **WHEN** source metadata 中包含 token、password、secret、邮箱或手机号
- **THEN** 落库 payload 中的敏感值被现有 trace payload safety 规则脱敏

### Requirement: Empty injected context is skipped
系统 SHALL 在没有实际注入来源时跳过 injected_context trace event。

#### Scenario: Empty sources are not recorded
- **WHEN** 调用 `record_injected_context(run_id="run-1", sources=[])`
- **THEN** 系统不写入 injected_context trace event

### Requirement: Agent runtime records injected context sources
agent-runtime SHALL 在 long-term-ctx 注入长期上下文后记录实际注入的来源摘要。

#### Scenario: Run id is shared across injected context and completion
- **WHEN** 一次 agent run 同时写入 injected_context 和 agent_run_completed trace events
- **THEN** 两类事件使用同一个 run_id

#### Scenario: Non-streaming run records sources
- **WHEN** `agent_loop.run()` 从 long-term-ctx 得到非空 `BuiltContext.sources`
- **THEN** 系统调用 `record_injected_context()` 记录这些 sources

#### Scenario: Streaming run records sources
- **WHEN** `agent_loop.run_stream()` 从 long-term-ctx 得到非空 `BuiltContext.sources`
- **THEN** 系统调用 `record_injected_context()` 记录这些 sources

#### Scenario: Agent runtime skips empty sources
- **WHEN** long-term-ctx 返回空 sources
- **THEN** agent-runtime 不写 injected_context trace event

### Requirement: Injected context events are queryable
injected_context events SHALL 通过现有 trace query API 查询，不引入单独查询表。

#### Scenario: Query injected context events
- **WHEN** 调用 `query_trace_events(TraceQuery(event_type="injected_context"))`
- **THEN** 返回匹配的来源归因 trace events
