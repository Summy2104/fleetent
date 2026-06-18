# observability-admin-api Specification

## Purpose
TBD - created by archiving change complete-admin-api-coverage. Update Purpose after archive.
## Requirements
### Requirement: 多维 trace 查询 HTTP API

平台 SHALL 在 `/admin/observability/traces` 暴露原始 trace 事件查询端点，包装 `fleetent.observability.query_trace_events` 公共 API，MUST 保留 CLI `observability traces` 的全部过滤维度：`run_id`、`user_id`、`agent`、`session_id`、`tenant_id`、`event_type`、时间窗（`since`/`until`）、`limit`。端点 MUST 要求 admin 角色（session token 鉴权）。

#### Scenario: 按 run_id 查询 trace 事件

- **WHEN** admin 调用 `GET /admin/observability/traces?run_id=<id>`
- **THEN** 系统返回该 run 的 trace 事件列表（与 CLI `observability traces --run-id <id>` 等价）

#### Scenario: 多维组合过滤

- **WHEN** admin 调用 `GET /admin/observability/traces?agent=ops-bot&event_type=tool_call&since=<ts>&limit=50`
- **THEN** 系统按全部条件过滤并返回不超过 limit 条事件

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用该端点
- **THEN** 系统返回 403

### Requirement: usage 聚合 HTTP API

平台 SHALL 在 `/admin/observability/usage` 暴露 token/run 用量聚合端点，包装 `fleetent.observability.get_usage_summary`，保留 CLI `observability usage` 的过滤维度（agent / user / tenant / 时间窗）。返回 MUST 含 token 总量、run_count、by_model 分项。

#### Scenario: 查询某 agent 用量

- **WHEN** admin 调用 `GET /admin/observability/usage?agent=ops-bot&since=<ts>`
- **THEN** 系统返回该 agent 的 token 总量、run 数和按模型拆分的用量

### Requirement: performance 指标 HTTP API

平台 SHALL 在 `/admin/observability/performance` 暴露性能指标端点，包装 `fleetent.observability.get_performance_summary`，返回 MUST 含 p50/p95 延迟、failure_rate，以及 llm / tool / permission 分项指标。

#### Scenario: 查询 performance 指标

- **WHEN** admin 调用 `GET /admin/observability/performance?agent=ops-bot&since=<ts>`
- **THEN** 系统返回 p50/p95 延迟、失败率及 llm/tool/permission 分项

### Requirement: observability 端点是 CLI 等价替代

`/admin/observability/{traces,usage,performance}` 三端点 SHALL 共同覆盖 CLI `observability traces`/`usage`/`performance` 三命令的全部查询能力，使后者可被 `slim-admin-cli` 安全退役。

#### Scenario: CLI 能力被 HTTP 完整覆盖

- **WHEN** 对照 CLI 三命令的每个过滤维度与输出字段
- **THEN** HTTP 三端点均有等价参数与等价返回，无维度缺失

