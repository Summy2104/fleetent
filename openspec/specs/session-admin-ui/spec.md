# session-admin-ui Specification

## Purpose
Define the native React SPA requirements for session administration: browsing session lists and
details, and performing governed session operations without relying on the legacy admin console.
## Requirements
### Requirement: Sessions managed natively in the React SPA
The React admin SPA SHALL render the sessions domain natively (not a deep-link to legacy): list
sessions, open a session's detail, and perform governance actions against the existing admin API
including takeover, release, inject, force-end, clear, reset, and batch actions. High-risk actions
(force-end / clear / reset / batch) SHALL require a second confirmation. Write actions SHALL be
admin-only; viewers are read-only. No chat playground is provided.

#### Scenario: List sessions and open detail
- **WHEN** an admin opens the sessions view
- **THEN** sessions are listed via `GET /admin/sessions`
- **AND** opening a session calls `GET /admin/sessions/{session_id}` for detail

#### Scenario: Governance action with confirmation
- **WHEN** an admin force-ends, clears, or resets a session and confirms the second prompt
- **THEN** the SPA calls the matching endpoint (`POST /admin/sessions/{session_id}/force-end`,
  `/clear`, or `/reset`)
- **AND** the session reflects the change

#### Scenario: Viewer is read-only
- **WHEN** a viewer opens the sessions view
- **THEN** governance write controls (takeover / inject / force-end / clear / reset / batch) are
  hidden or denied
- **AND** the viewer can only browse

#### Scenario: Sessions no longer deep-link to legacy
- **WHEN** the SPA navigation is rendered
- **THEN** sessions is a native route
- **AND** sessions is not an entry in the legacy deep-link list
