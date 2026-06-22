## REMOVED Requirements

### Requirement: Observability admin trace query CLI
**Reason**: 迁移到 HTTP API `GET /admin/observability/traces`（由 `complete-admin-api-coverage` 提供），保留全部过滤维度。CLI 入口冗余。
**Migration**: 用 `GET /admin/observability/traces?run_id=&user_id=&agent=&session_id=&tenant_id=&event_type=&since=&until=&limit=` 替代 `fleetent-admin observability traces ...`。

#### Scenario: Query trace events by run id
- **WHEN** operator 运行 `fleetent-admin observability traces --run-id run-1 --event-type agent_run_completed --limit 20`
- **THEN** CLI 输出该 run 匹配的 trace events

#### Scenario: Query trace events by session id
- **WHEN** operator 运行 `fleetent-admin observability traces --session-id session-1`
- **THEN** CLI 输出该 session 的 trace events

### Requirement: Observability admin usage query CLI
**Reason**: 迁移到 `GET /admin/observability/usage`。
**Migration**: 用 `GET /admin/observability/usage?agent=&user_id=&tenant_id=&since=&until=` 替代。

#### Scenario: Query usage summary
- **WHEN** operator 运行 `fleetent-admin observability usage --user-id user-1 --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59`
- **THEN** CLI 输出 run count、token usage 和 model 分组

### Requirement: Observability admin performance query CLI
**Reason**: 迁移到 `GET /admin/observability/performance`。
**Migration**: 用 `GET /admin/observability/performance?agent=&since=&until=&limit=` 替代。

#### Scenario: Query performance summary
- **WHEN** operator 运行 `fleetent-admin observability performance --agent-id agent-1 --limit 100`
- **THEN** CLI 输出失败率、延迟、LLM / tool / permission 指标

### Requirement: Observability admin query rejects invalid time
**Reason**: 随 observability CLI 一并退役；时间参数校验由 HTTP 端点承担。
**Migration**: HTTP observability 端点对非法时间参数返回 422。

#### Scenario: Invalid time is rejected
- **WHEN** operator 运行 `fleetent-admin observability usage --from not-a-time`
- **THEN** CLI 报时间格式错误并非 0 退出
