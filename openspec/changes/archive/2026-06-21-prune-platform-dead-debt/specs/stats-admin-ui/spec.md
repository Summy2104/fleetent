## MODIFIED Requirements

### Requirement: Export and reports
The console SHALL let an admin trigger a stats export. Report generation is not offered (there is no `POST /admin/stats/reports` endpoint).

#### Scenario: Trigger export
- **WHEN** an admin clicks export
- **THEN** the console calls `POST /admin/stats/export`
