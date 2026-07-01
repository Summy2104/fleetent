# session-admin-console Specification

## Purpose
记录 platform sessions 治理控制面的退役结果，以及保留的替代入口边界。

## Requirements

### Requirement: Platform sessions governance endpoints are retired
The platform SHALL NOT expose the legacy `/admin/sessions/*` governance endpoints. Session list, takeover, inject, force-end, clear, reset, bulk disposal, and transcript export are retired because their management-db/session-file seams were never live in managed deployments. The retained operator entry point for per-session inspection is `GET /admin/stats/sessions/{session_id}/trace`.

#### Scenario: Sessions governance routes are absent
- **WHEN** the platform server mounts admin routers
- **THEN** no `/admin/sessions/*` route is registered
- **AND** `GET /admin/stats/sessions/{session_id}/trace` remains available for trace inspection
