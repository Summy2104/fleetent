## ADDED Requirements

### Requirement: Trace event public API
系统 SHALL 提供明确的 agent run trace public API：`record_trace_event(event)`、
`query_trace_events(query)`、`TraceEvent` 和 `TraceQuery`。

#### Scenario: Record trace event API exists
- **WHEN** 调用方从 `fleetent.observability` 导入 `record_trace_event` 和 `TraceEvent`
- **THEN** 导入成功，且可构造一条 trace event

#### Scenario: Query trace events API exists
- **WHEN** 调用方从 `fleetent.observability` 导入 `query_trace_events` 和 `TraceQuery`
- **THEN** 导入成功，且可构造查询条件

### Requirement: No legacy trace logging API
系统 SHALL 删除旧的 JSONL trace API，不保留向后兼容 wrapper。

#### Scenario: Legacy eval_logger import removed
- **WHEN** 调用方导入 `fleetent.eval_logger`
- **THEN** 导入失败或明确不可用

#### Scenario: Legacy trace functions are not public
- **WHEN** 调用方从 `fleetent.observability` 导入 `log_run`、`log` 或 `TRACE_PATH`
- **THEN** 导入失败或对应名称不存在

### Requirement: Trace table storage
系统 SHALL 将 agent run trace events 存储在 observability-owned SQLite `traces` 表中。

#### Scenario: Migration creates trace table
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 `traces` 表

#### Scenario: Migration creates trace indexes
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含按 run、user/time、agent/time、tenant/event/time 查询所需索引

### Requirement: Record trace event
`record_trace_event()` SHALL 写入一条 trace event，并在缺省情况下生成 event id 与 timestamp。

#### Scenario: Record event with generated id and timestamp
- **WHEN** 调用 `record_trace_event()` 写入未携带 id 和 ts 的 `TraceEvent`
- **THEN** `traces` 表中出现一条带 id 和 ts 的记录

#### Scenario: Payload is persisted as JSON
- **WHEN** trace event 带有 payload
- **THEN** payload 被序列化到 `payload_json`

### Requirement: Query trace events
`query_trace_events()` SHALL 支持按 run、user、agent、tenant、event_type、时间范围和 limit 查询 trace events。

#### Scenario: Query by run id
- **WHEN** 调用 `query_trace_events(TraceQuery(run_id="run-1"))`
- **THEN** 只返回 `run_id` 为 `run-1` 的事件

#### Scenario: Query by agent and time range
- **WHEN** 调用 `query_trace_events()` 并传入 agent_id、start_ts 和 end_ts
- **THEN** 只返回该 agent 在时间范围内的事件

#### Scenario: Query limit
- **WHEN** 查询条件包含 `limit=10`
- **THEN** 最多返回 10 条事件

### Requirement: Trace payload safety
系统 SHALL 在 trace payload 落库前执行脱敏、截断和 JSON 序列化 fallback。

#### Scenario: Sensitive payload values are redacted
- **WHEN** payload 中包含 token、password、secret、邮箱或手机号
- **THEN** 落库内容中的敏感值被不可逆脱敏

#### Scenario: Large payload values are truncated
- **WHEN** payload 中包含超过阈值的大字段
- **THEN** 落库内容被截断，并包含截断标记

#### Scenario: Non-serializable payload has fallback
- **WHEN** payload 中包含不可 JSON 序列化对象
- **THEN** 系统将该值转换为字符串，并标记 `serialization_fallback=true`

### Requirement: Agent runtime records completed run
agent-runtime SHALL 在 run 完成后记录 `agent_run_completed` trace event。

#### Scenario: Non-streaming run records trace
- **WHEN** `agent_loop.run()` 成功完成
- **THEN** 系统写入一条 `event_type=agent_run_completed` 的 trace event

#### Scenario: Streaming run records trace with usage
- **WHEN** `agent_loop.run_stream()` 成功完成并获得 token usage
- **THEN** 系统写入一条包含 token usage 的 `agent_run_completed` trace event

### Requirement: No JSONL trace output
系统 SHALL 不再创建或追加 `data/traces.jsonl`。

#### Scenario: Agent run does not write JSONL
- **WHEN** 任意 agent run 完成
- **THEN** 系统不会创建或追加 `data/traces.jsonl`

### Requirement: Trace and structured logging naming separation
系统 SHALL 将 `log` 命名留给 structured logging，不用于 agent run trace public API。

#### Scenario: Trace API does not expose log names
- **WHEN** 调用方查看 `fleetent.observability` public API
- **THEN** agent trace 相关能力通过 `record_trace_event` 和 `query_trace_events` 暴露，而不是 `log` 或 `log_run`
