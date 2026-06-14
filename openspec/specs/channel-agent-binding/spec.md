# channel-agent-binding Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
### Requirement: Management DB excludes channel-agent binding capability
The management database MUST NOT expose a `channel_agents` table or any direct channel-to-agent
binding API surface.

#### Scenario: Head schema and admin surface exclude channel bindings
- **WHEN** management DB migrations are applied to head and the admin surface is exercised
- **THEN** no `channel_agents` table exists
- **AND** no channel binding CRUD endpoint or CLI command is available

