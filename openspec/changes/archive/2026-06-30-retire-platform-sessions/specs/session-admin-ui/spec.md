## REMOVED Requirements

### Requirement: Sessions managed natively in the React SPA
**Reason**: 前端 sessions 治理 feature 随后端 `session-admin-console` capability 整体退场。该视图调用的 `/admin/sessions/*` endpoint 被移除，且后端列表数据源生产恒空，页面无任何可展示数据。
**Migration**: 移除 `features/sessions/` 整目录、`/sessions` 路由与导航项、`sessions.*` / `nav.sessions` i18n 词条。需查看单会话 trace 的入口保留在 `stats-admin-ui`（消费 `GET /admin/stats/sessions/{session_id}/trace`），不受影响。
