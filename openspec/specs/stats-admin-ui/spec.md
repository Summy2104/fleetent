# stats-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Statistics tab
The admin console SHALL present a Statistics tab showing per-agent overview, per-user usage, and a request list, sourced from `/admin/stats` endpoints.

#### Scenario: Admin sees per-user stats
- **WHEN** an admin opens the Statistics tab
- **THEN** per-user usage is shown via `GET /admin/stats/per-user`

#### Scenario: Agent overview
- **WHEN** an admin selects an agent
- **THEN** its overview is shown via `GET /admin/stats/agents/{agent_id}/overview`

### Requirement: Request drill-down and trace
The console SHALL let an admin open a request's detail and a session's trace.

#### Scenario: View a session trace
- **WHEN** an admin opens a session trace
- **THEN** the console calls `GET /admin/stats/sessions/{session_id}/trace` and renders it

### Requirement: Export and reports
The console SHALL let an admin trigger a stats export and generate a report.

#### Scenario: Trigger export
- **WHEN** an admin clicks export
- **THEN** the console calls `POST /admin/stats/export`
