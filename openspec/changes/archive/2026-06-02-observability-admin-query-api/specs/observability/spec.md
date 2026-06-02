## ADDED Requirements

### Requirement: Observability admin trace query CLI
系统 SHALL 在 `fleetent-admin` 中提供 observability trace 查询命令，使 operator 无需手写 SQL 即可查询 agent run trace events。

#### Scenario: Query traces by filters
- **WHEN** operator 运行 `fleetent-admin observability traces --run-id run-1 --event-type agent_run_completed --limit 20`
- **THEN** CLI 调用 observability public API `query_trace_events(TraceQuery(...))`
- **AND** 查询条件包含 run_id、event_type 和 limit

#### Scenario: Query traces by session
- **WHEN** operator 运行 `fleetent-admin observability traces --session-id session-1`
- **THEN** CLI 调用 observability public API `query_trace_events(TraceQuery(session_id="session-1"))`

#### Scenario: Trace output is bounded
- **WHEN** trace event payload 包含 prompt、reply、tool payload、token、secret 或 credential 字段
- **THEN** CLI 输出不包含 payload 原值
- **AND** CLI 只展示事件元数据和 bounded payload key summary

### Requirement: Observability admin usage query CLI
系统 SHALL 在 `fleetent-admin` 中提供 usage summary 查询命令，使 operator 能查看 run count、token usage 和 model 分组。

#### Scenario: Query usage summary by filters
- **WHEN** operator 运行 `fleetent-admin observability usage --user-id user-1 --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59`
- **THEN** CLI 调用 observability public API `get_usage_summary(UsageQuery(...))`
- **AND** 输出包含 run count、prompt tokens、completion tokens、total tokens 和 by-model summary

### Requirement: Observability admin performance query CLI
系统 SHALL 在 `fleetent-admin` 中提供 performance summary 查询命令，使 operator 能查看失败率、延迟、LLM / tool / permission 指标。

#### Scenario: Query performance summary by filters
- **WHEN** operator 运行 `fleetent-admin observability performance --agent-id agent-1 --limit 100`
- **THEN** CLI 调用 observability public API `get_performance_summary(PerformanceQuery(...))`
- **AND** 输出包含 run count、failure rate、latency percentile、LLM、tool、fallback 和 permission summary

### Requirement: Observability admin query rejects invalid time
系统 SHALL 对 observability admin query 的非法时间过滤给出明确错误并以非零状态退出。

#### Scenario: Invalid from timestamp
- **WHEN** operator 运行 `fleetent-admin observability usage --from not-a-time`
- **THEN** CLI 输出 invalid timestamp 错误
- **AND** 进程以非零状态退出
