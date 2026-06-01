## ADDED Requirements

### Requirement: Performance summary public API
系统 SHALL 提供 performance summary public API，用于从 runtime trace events 聚合性能和失败指标。

#### Scenario: Performance API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `PerformanceQuery`、`PerformanceSummary` 和 `get_performance_summary`
- **THEN** 导入成功

#### Scenario: Empty performance summary
- **WHEN** 查询范围内没有 trace events
- **THEN** summary 的计数、耗时、错误率和分组列表均为 0 或空列表

### Requirement: Performance summary reads through trace API
performance summary SHALL 通过 `query_trace_events()` 读取 traces，而不是直接访问 SQLite `traces` 表。

#### Scenario: Performance summary uses trace query API
- **WHEN** `get_performance_summary()` 执行查询
- **THEN** 它调用 `query_trace_events()`，并传入 query filters

### Requirement: Performance query filters
系统 SHALL 支持按 user、agent、tenant、session、时间范围和 limit 过滤 performance summary。

#### Scenario: Filter by user
- **WHEN** 调用 `get_performance_summary(PerformanceQuery(user_id="user-1"))`
- **THEN** summary 只统计 user-1 的 trace events

#### Scenario: Filter by session
- **WHEN** 查询包含 session_id
- **THEN** summary 只统计该 session 的 trace events

#### Scenario: Filter by agent and time range
- **WHEN** 查询包含 agent_id、start_ts 和 end_ts
- **THEN** summary 只统计该 agent 在时间范围内的 trace events

### Requirement: Run-level performance metrics
系统 SHALL 从 agent run lifecycle events 聚合 run-level performance metrics。

#### Scenario: Run counts and failure rate
- **WHEN** traces 中包含 completed 和 failed runs
- **THEN** summary 返回 run_count、completed_count、failed_count 和 failure_rate

#### Scenario: Run latency percentiles
- **WHEN** completed 或 failed run events 包含 elapsed_s
- **THEN** summary 返回 avg_elapsed_s、p50_elapsed_s 和 p95_elapsed_s

### Requirement: LLM and fallback metrics
系统 SHALL 从 LLM runtime events 聚合 LLM 调用、错误、耗时和 fallback 指标。

#### Scenario: LLM call metrics
- **WHEN** traces 中包含 `llm_call_completed` 和 `llm_call_failed`
- **THEN** summary 返回 llm_call_count、llm_error_count、avg_llm_elapsed_s 和 p95_llm_elapsed_s

#### Scenario: Fallback metrics
- **WHEN** traces 中包含 `model_fallback_triggered`
- **THEN** summary 返回 fallback_count 和 fallback_rate

#### Scenario: Group by model
- **WHEN** LLM events 包含多个 model
- **THEN** summary.by_model 按 model 返回 call_count、error_count 和 avg_elapsed_s

### Requirement: Tool performance metrics
系统 SHALL 从 tool runtime events 聚合工具调用、错误和耗时指标。

#### Scenario: Tool call metrics
- **WHEN** traces 中包含 `tool_call_completed` 和 `tool_call_failed`
- **THEN** summary 返回 tool_call_count、tool_error_count、avg_tool_elapsed_s 和 p95_tool_elapsed_s

#### Scenario: Group by tool
- **WHEN** tool events 包含多个 tool_name
- **THEN** summary.by_tool 按 tool_name 返回 call_count、error_count 和 avg_elapsed_s
- **AND** by_tool 按 call_count 降序、tool_name 升序稳定排序

### Requirement: Permission wait metrics
系统 SHALL 从 permission runtime events 聚合人工审批数量和等待耗时。

#### Scenario: Permission decisions are counted
- **WHEN** traces 中包含 `permission_resolved` events
- **THEN** summary 返回 permission_requested_count、permission_approved_count、permission_rejected_count 和 permission_timeout_count

#### Scenario: Permission wait time is averaged
- **WHEN** permission resolved events 包含 elapsed_s
- **THEN** summary 返回 avg_permission_wait_s

### Requirement: Performance payload tolerance
系统 SHALL 容忍旧 trace、不完整 trace 或非法 payload 字段。

#### Scenario: Missing elapsed counts as zero
- **WHEN** runtime event payload 缺失 elapsed_s
- **THEN** latency aggregation treats it as 0 and does not raise

#### Scenario: Invalid numeric fields are ignored
- **WHEN** runtime event payload 中的 elapsed_s 或计数字段不是合法数字
- **THEN** summary treats that value as 0 and does not raise

#### Scenario: Missing grouping keys use unknown
- **WHEN** LLM event 缺失 model 或 tool event 缺失 tool_name
- **THEN** 对应分组归入 `unknown`
