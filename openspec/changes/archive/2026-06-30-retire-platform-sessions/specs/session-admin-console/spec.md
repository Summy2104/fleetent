## REMOVED Requirements

### Requirement: Session list and search
**Reason**: 会话治理后端整体退场。列表唯一数据源 `session_meta` 表的写入入口 `upsert_meta` 在生产代码零调用方，列表恒空，功能从未真正可用。
**Migration**: 无下游消费方（前端 sessions feature 同步移除）。需查看单会话 trace 改用 `agent-stats-aggregation` 的 `GET /admin/stats/sessions/{session_id}/trace`（保留，不属本 capability）。

### Requirement: Per-turn replay reuses read-only browsing
**Reason**: 同上，治理控制台退场。managed 解耦拓扑下 platform 无跨 node session 通道，transcript 回放恒空。
**Migration**: 无下游消费方。

### Requirement: Session takeover with human injection
**Reason**: 同上。takeover/inject 依赖的 `im_deliver` seam 始终是 no-op，injection 从不回投 IM。
**Migration**: 无下游消费方。

### Requirement: Force-end / clear / reset
**Reason**: 同上。这些写操作在 managed 拓扑下作用于 platform 本地不存在的 session 文件，静默无效。
**Migration**: 无下游消费方。agent 侧 session 生命周期维护由 `internal-session-maintenance` / `session-ttl-cleanup` 承担，不受影响。

### Requirement: Batch disposal and quota linkage
**Reason**: 同上，依赖恒空的会话列表，批量操作无对象。
**Migration**: 无下游消费方。

### Requirement: Export with audit trail
**Reason**: 同上。导出依赖恒空的 transcript；纯渲染函数 `transcript_export.render_markdown` 仅被自身测试引用，未接任何 endpoint。
**Migration**: 无下游消费方。

### Requirement: Chat management permissions and audit
**Reason**: 同上，整个治理 capability 退场后无需独立的权限/审计约束。
**Migration**: 无下游消费方。平台审计能力由 `platform-audit-log` 继续承担。
