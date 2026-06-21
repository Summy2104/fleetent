# session-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Sessions tab
The admin console SHALL present a Sessions tab listing sessions from `GET /admin/sessions` and letting an admin open a session's detail.

#### Scenario: Admin sees sessions list
- **WHEN** an admin opens the Sessions tab
- **THEN** sessions are listed via `GET /admin/sessions`

#### Scenario: Viewer cannot control sessions
- **WHEN** a viewer opens the Sessions tab
- **THEN** takeover / release / inject / force-end / clear / reset controls are hidden

### Requirement: Session control actions
The console SHALL let an admin take over, release, inject a message, force-end, clear, and reset a session, calling the matching endpoints.

#### Scenario: Take over a session
- **WHEN** an admin takes over a session
- **THEN** the console calls `POST /admin/sessions/{session_id}/takeover`

#### Scenario: Force-end a session
- **WHEN** an admin force-ends a session
- **THEN** the console calls `POST /admin/sessions/{session_id}/force-end`
