# observability-admin-query-api

## 背景

Pilot MVP 要求 operator 能在不手写 SQL 的情况下排查 agent run、usage 和性能问题。当前
observability 已提供 Python public API：`query_trace_events()`、`get_usage_summary()` 和
`get_performance_summary()`，但 `fleetent-admin` 还没有面向运维的查询入口。

## 目标

- 在 `fleetent-admin` 中新增 `observability` 子命令，提供 trace、usage 和 performance 查询。
- 查询入口复用 observability public API，不直接访问 SQLite 表。
- 输出只包含 bounded summary，不输出完整 prompt、reply、tool payload、secret 或 credential。
- 提供可组合的 filter：run、user、agent、tenant、session、event type、时间范围和 limit。

## 非目标

- 不新增 platform UI。
- 不新增 HTTP API。
- 不新增 rollup 表、后台任务或缓存。
- 不改变 trace 写入 schema。

## 模块边界影响

- owning package：`observability` owns 查询语义；`admin.py` 只是 CLI adapter。
- public API surface：为 `TraceQuery` 增加可选 `session_id` filter；复用 `query_trace_events()`、
  `UsageQuery`、`get_usage_summary()`、`PerformanceQuery`、`get_performance_summary()`；新增的
  CLI helper 函数不作为跨模块 public API。
- owned tables：无新增；继续读取 observability-owned `traces` 表，但只能通过 public API。
- config namespace：无新增配置。
- cross-module dependencies：`fleetent.admin` 依赖 `fleetent.observability` public API。
- migration / shim plan：无数据库迁移；MVP 阶段不做旧命令 shim。

## 风险与缓解

- 风险：CLI 输出误带敏感 payload。
  - 缓解：trace list 默认只展示 event metadata 和 payload top-level keys，不展示 payload value。
- 风险：查询量过大影响本地 SQLite。
  - 缓解：所有命令提供 limit，默认保守限制。
