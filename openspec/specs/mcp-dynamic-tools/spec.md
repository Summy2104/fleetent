# mcp-dynamic-tools Specification

## Purpose
TBD - created by archiving change mcp-list-changed. Update Purpose after archive.
## Requirements
### Requirement: Refresh stdio tools on list_changed

When a connected stdio MCP server sends a `notifications/tools/list_changed` notification, the client SHALL re-discover that server's tools and update its registered tools accordingly (adding new tools, removing withdrawn ones) without requiring a restart. The refresh SHALL run in a task separate from the notification handler, so the handler never issues a request on the stream while still processing — avoiding a stdio-stream deadlock.

#### Scenario: New tool appears after notification
- **WHEN** a stdio server that initially exposed tool `a` later exposes `a` and `b` and emits `tools/list_changed`
- **THEN** after the refresh the registry contains both `{server}__a` and `{server}__b`

#### Scenario: Withdrawn tool removed after notification
- **WHEN** a stdio server that exposed `a` and `b` later exposes only `a` and emits `tools/list_changed`
- **THEN** after the refresh the registry no longer contains `{server}__b`

#### Scenario: Non-list-changed messages ignored
- **WHEN** the client receives a server message that is not a `tools/list_changed` notification
- **THEN** no tool refresh is triggered

### Requirement: Refresh is identity-guarded and deduplicated

A tool refresh SHALL apply only when the session that produced the notification is still the server's current session, so a notification from a session that has since been replaced (e.g. after a reconnect) is ignored. Concurrent refreshes for the same server SHALL be coalesced so a burst of notifications does not run overlapping refreshes.

#### Scenario: Stale-session notification ignored
- **WHEN** a `tools/list_changed`-driven refresh is requested for a session that is no longer the server's active session
- **THEN** the registry is left unchanged

#### Scenario: Re-registration is consistent
- **WHEN** a refresh re-registers a server's tools
- **THEN** the server's registered tool set exactly matches the freshly discovered tool list (no leftover stale tools, no duplicates)

