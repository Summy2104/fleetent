# observability Delta

## MODIFIED Requirements

### Requirement: Query trace events
`query_trace_events()` SHALL 支持按 run、user、agent、tenant、event_type、时间范围和 limit 查询 trace events。其中 agent 维度字段为 `agent_name`（agent 侧 trace 以 agent slug/name 记，列名为 `agent_name`，不再叫 `agent_id`——身份模型 R2：agent 侧不出现 agent id）。

#### Scenario: Query by run id
- **WHEN** 调用 `query_trace_events(TraceQuery(run_id="run-1"))`
- **THEN** 只返回 `run_id` 为 `run-1` 的事件

#### Scenario: Query by agent and time range
- **WHEN** 调用 `query_trace_events()` 并传入 `agent_name`、start_ts 和 end_ts
- **THEN** 只返回该 agent 在时间范围内的事件

#### Scenario: Query limit
- **WHEN** 查询条件包含 `limit=10`
- **THEN** 最多返回 10 条事件
