## MODIFIED Requirements

### Requirement: Chat management permissions and audit

Session takeover / injection / force-end / clear / reset / export SHALL be admin-only. Viewers SHALL be limited to read-only browsing and replay. High-risk actions SHALL require a second confirmation, and all write operations SHALL be audited (who / when / which session / what).

#### Scenario: Viewer is read-only

- **WHEN** a viewer opens chat and attempts to take over / clear a session
- **THEN** the action's button is hidden or returns 403; the viewer can only browse the session list and per-turn replay
