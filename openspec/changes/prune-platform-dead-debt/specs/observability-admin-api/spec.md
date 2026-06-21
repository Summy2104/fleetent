## REMOVED Requirements

### Requirement: 多维 trace 查询 HTTP API

**Reason**: `/admin/observability/traces` 无任何 UI / CLI / 测试调用方；admin 控制台的分析功能全部走 `stats-admin-api`（`/admin/stats/*`）。该端点为孤儿。

**Migration**: trace 钻取改用 `GET /admin/stats/sessions/{session_id}/trace` 与 `GET /admin/stats/requests/{request_id}`；命令行仍可用 CLI `observability traces` 的全部过滤维度。

### Requirement: usage 聚合 HTTP API

**Reason**: `/admin/observability/usage` 无调用方；用量分析由 `GET /admin/stats/per-user` 与 `GET /admin/stats/agents/{agent_id}/overview` 提供。

**Migration**: 用 `/admin/stats/*` 用量端点；命令行仍可用 CLI `observability usage`。

### Requirement: performance 指标 HTTP API

**Reason**: `/admin/observability/performance` 无调用方；性能视图未在控制台暴露。

**Migration**: 命令行仍可用 CLI `observability performance`。

### Requirement: observability 端点是 CLI 等价替代

**Reason**: 该 requirement 的前提是「让 CLI `observability` 命令退役」，但 CLI 命令并未退役、仍是 observability 查询入口；HTTP 三端点既无消费者、亦未触发 CLI 退役，目标落空。

**Migration**: observability 查询继续以 CLI `observability traces/usage/performance` 为入口；控制台分析以 `stats-admin-api` 为入口。两者并存，无需该等价层。
