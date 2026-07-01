# session-admin-ui Specification

## Purpose
记录 admin SPA 中 sessions 面的退役结果，以及保留的替代入口边界。

## Requirements

### Requirement: Sessions governance view is retired from the SPA
The React admin SPA SHALL NOT expose a native `/sessions` route, sessions navigation item, or the removed `sessions.*` translations. The frontend SHALL rely on the retained statistics trace flow for per-session inspection instead of the retired sessions governance surface.

#### Scenario: Navigation omits sessions
- **WHEN** the SPA navigation and routes are rendered
- **THEN** there is no `/sessions` route or navigation item
- **AND** the statistics flow continues to call `GET /admin/stats/sessions/{session_id}/trace` for per-session trace inspection
