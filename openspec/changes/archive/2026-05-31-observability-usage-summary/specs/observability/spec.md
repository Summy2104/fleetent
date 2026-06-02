## ADDED Requirements

### Requirement: Usage summary public API
系统 SHALL 提供 usage summary public API，用于从 agent run traces 聚合调用次数、token 用量和耗时。

#### Scenario: Usage API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `UsageQuery`、`UsageSummary`、`ModelUsage` 和 `get_usage_summary`
- **THEN** 导入成功

### Requirement: Usage summary source events
usage summary SHALL 只统计 `agent_run_completed` trace events。

#### Scenario: Ignore other event types
- **WHEN** traces 中同时存在 `agent_run_completed` 和其他 event_type
- **THEN** usage summary 只统计 `agent_run_completed`

### Requirement: Basic usage aggregation
系统 SHALL 聚合 run_count、prompt_tokens、completion_tokens、total_tokens、total_elapsed_s 和 avg_elapsed_s。

#### Scenario: Empty usage summary
- **WHEN** 查询范围内没有 completed run
- **THEN** summary 的 run_count、tokens、elapsed 和 average 均为 0

#### Scenario: Aggregate multiple runs
- **WHEN** 查询范围内有多条 completed run trace
- **THEN** summary 返回这些 run 的数量、token 总和、elapsed 总和和平均 elapsed

### Requirement: Usage query filters
系统 SHALL 支持按 user、agent、tenant、session 和时间范围过滤 usage summary。

#### Scenario: Filter by user
- **WHEN** 调用 `get_usage_summary(UsageQuery(user_id="user-1"))`
- **THEN** summary 只包含 user-1 的 completed runs

#### Scenario: Filter by agent and time range
- **WHEN** 查询包含 agent_id、start_ts 和 end_ts
- **THEN** summary 只包含该 agent 在时间范围内的 completed runs

#### Scenario: Filter by session
- **WHEN** 查询包含 session_id
- **THEN** summary 只包含该 session 的 completed runs

### Requirement: Usage by model
系统 SHALL 按 model 聚合 usage，并返回稳定排序的 `by_model` 列表。

#### Scenario: Group usage by model
- **WHEN** completed runs 使用多个 model
- **THEN** summary.by_model 按 model 分别返回 run_count、tokens 和 elapsed

#### Scenario: Sort model usage
- **WHEN** 返回多个 model usage
- **THEN** by_model 按 total_tokens 降序排列；total_tokens 相同时按 model 升序排列

### Requirement: Usage payload tolerance
系统 SHALL 容忍旧 trace 或不完整 trace 中缺失或非法的 usage payload 字段。

#### Scenario: Missing token usage counts as zero
- **WHEN** completed run payload 缺失 tokens 字段
- **THEN** token 聚合按 0 处理，不抛出异常

#### Scenario: Missing elapsed counts as zero
- **WHEN** completed run payload 缺失 elapsed_s
- **THEN** elapsed 聚合按 0 处理，不抛出异常

#### Scenario: Missing model groups as unknown
- **WHEN** completed run payload 缺失 model_used
- **THEN** 该 run 归入 model=`unknown`

### Requirement: Usage summary reads through trace API
usage summary SHALL 通过 `query_trace_events()` 读取 traces，而不是直接访问 SQLite `traces` 表。

#### Scenario: Usage summary uses trace query API
- **WHEN** `get_usage_summary()` 执行查询
- **THEN** 它调用 `query_trace_events()`，并传入 event_type=`agent_run_completed`
