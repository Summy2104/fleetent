## ADDED Requirements

### Requirement: Sessions managed natively in the React SPA

The React admin SPA SHALL render the sessions domain natively (not a deep-link to legacy): list sessions, open a session's detail, and perform governance actions against the existing admin API — take over, release, inject a message, force-end, clear, reset, and batch actions. High-risk actions (force-end / clear / reset / batch) SHALL require a second confirmation. Write actions SHALL be admin-only; viewers are read-only. No chat playground is provided (removed in prune-platform-dead-debt).

#### Scenario: List sessions and open detail

- **WHEN** an admin opens the sessions view
- **THEN** sessions are listed via `GET /admin/sessions` and opening one calls `GET /admin/sessions/{id}` for detail

#### Scenario: Governance action with confirmation

- **WHEN** an admin force-ends, clears, or resets a session and confirms the second prompt
- **THEN** the SPA calls the matching endpoint (`POST /admin/sessions/{id}/force-end`|`/clear`|`/reset`) and the session reflects the change

#### Scenario: Viewer is read-only

- **WHEN** a viewer opens the sessions view
- **THEN** governance write controls (takeover/inject/force-end/clear/reset/batch) are hidden or denied; the viewer can only browse

#### Scenario: Sessions no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** sessions is a native route, not an entry in the legacy deep-link list
