## ADDED Requirements

### Requirement: Channel allowlist storage
The system SHALL store allowed message scopes in an `im_channel_allowlist` table with columns: `id`, `platform` (TEXT), `scope_type` (TEXT — `channel` or `workspace`), `scope_id` (TEXT — the channel id or workspace/team id), `allowed` (INTEGER default 1), `note` (TEXT, nullable), `created_at`, with a UNIQUE constraint on `(platform, scope_type, scope_id)`.

#### Scenario: Table initialized
- **WHEN** `_init_db()` runs on a fresh database
- **THEN** the `im_channel_allowlist` table exists with a UNIQUE constraint on `(platform, scope_type, scope_id)`

#### Scenario: Add allow entry
- **WHEN** an admin adds `(platform="slack", scope_type="channel", scope_id="C_ops")`
- **THEN** a row is inserted with `allowed=1`

#### Scenario: Duplicate scope upserts
- **WHEN** an entry for the same `(platform, scope_type, scope_id)` is added again
- **THEN** the existing row is updated (upsert), not duplicated

### Requirement: Per-platform opt-in enforcement
Allowlist enforcement SHALL be controlled per platform by `im_connectors.allowlist_enforced`. When 0, `is_allowed` SHALL return true for any channel (backward compatible with the current MVP). When 1, only channels/workspaces with a matching `allowed=1` entry SHALL be permitted.

#### Scenario: Enforcement disabled allows all
- **WHEN** `slack` has `allowlist_enforced=0` and a message arrives in any channel
- **THEN** `im_channel_allowlist.is_allowed("slack", channel_id, workspace_id)` returns true

#### Scenario: Enforcement enabled, channel listed
- **WHEN** `slack` has `allowlist_enforced=1` and channel `C_ops` has an `allowed=1` entry
- **THEN** a message in `C_ops` is allowed

#### Scenario: Enforcement enabled, channel not listed
- **WHEN** `slack` has `allowlist_enforced=1` and a message arrives in a channel with no matching entry
- **THEN** `is_allowed` returns false

#### Scenario: Workspace-level allow covers its channels
- **WHEN** `allowlist_enforced=1` and a `workspace`-scoped `allowed=1` entry exists for the message's workspace/team
- **THEN** a message in any channel of that workspace is allowed even without a channel-level entry

### Requirement: Routing enforces the channel allowlist before the agent pipeline
Message routing SHALL check the channel allowlist before user-level checks and agent resolution. Disallowed messages SHALL NOT enter the agent pipeline.

#### Scenario: Disallowed channel is rejected pre-pipeline
- **WHEN** a message arrives in a channel that `is_allowed` returns false for
- **THEN** the adapter replies with a rejection and the message does NOT reach `get_agent_for_context` / the agent loop

#### Scenario: Allowed channel proceeds to user check
- **WHEN** `is_allowed` returns true
- **THEN** routing proceeds to the existing IM user allowlist check and agent resolution

### Requirement: Allowlist management surface
The system SHALL expose listing, adding, and removing allowlist entries via admin API and CLI.

#### Scenario: List by platform
- **WHEN** an admin lists the allowlist filtered by `platform=slack`
- **THEN** all `slack` entries are returned with their `scope_type`, `scope_id`, `allowed`, `note`

#### Scenario: Remove entry
- **WHEN** an admin removes an allowlist entry by id
- **THEN** the row is deleted and subsequent messages for that scope follow the platform's enforcement policy
