## ADDED Requirements

### Requirement: Statistics managed natively in the React SPA

The React admin SPA SHALL render the Statistics domain natively (not a deep-link to legacy), backed by the existing read-only `/admin/stats` API: per-agent overview, per-user usage, agent comparison, per-user request lists, request detail, session trace, and stats export. It SHALL NOT call a report-generation endpoint (none exists).

#### Scenario: View per-user and agent overview

- **WHEN** an admin opens the Statistics view
- **THEN** per-user usage is shown via `GET /admin/stats/per-user` and a selected agent's overview via `GET /admin/stats/agents/{id}/overview`

#### Scenario: Drill into a request / session trace

- **WHEN** an admin opens a request or a session trace
- **THEN** the SPA calls `GET /admin/stats/requests/{id}` (resp. `GET /admin/stats/sessions/{id}/trace`) and renders it

#### Scenario: Export

- **WHEN** an admin triggers an export
- **THEN** the SPA calls `POST /admin/stats/export` and delivers the result

#### Scenario: Statistics no longer deep-links to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Statistics is a native route, not an entry in the legacy deep-link list
