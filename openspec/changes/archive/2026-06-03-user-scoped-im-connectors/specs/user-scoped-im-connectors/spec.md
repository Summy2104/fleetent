## ADDED Requirements

### Requirement: Per-owner connector registry
The IM connector registry SHALL store connectors keyed by `(owner_id, platform)` so each
platform user (owner) can register their own connector per platform and multiple owners'
connectors for the same platform coexist.

#### Scenario: Two owners register the same platform
- **WHEN** owner A and owner B each create a Slack connector
- **THEN** both rows persist independently, each keyed by its own `owner_id`, and neither
  overwrites the other

#### Scenario: Owner reads only own connector by default
- **WHEN** a non-admin owner lists connectors
- **THEN** only that owner's connectors are returned

### Requirement: Owner-scoped credential resolution with admin-only env fallback
Connector credential resolution SHALL be scoped by `owner_id`. The `.env` fallback SHALL
apply only to the built-in admin owner; any other owner without stored config SHALL
resolve to no credentials and report `unconfigured`.

#### Scenario: Admin owner inherits env credentials
- **WHEN** the admin owner has no DB config but `.env` provides a bot token
- **THEN** resolution returns the env credentials

#### Scenario: Non-admin owner does not inherit env
- **WHEN** a non-admin owner has no DB config
- **THEN** resolution returns empty and the connector is `unconfigured`

### Requirement: Per-owner adapter lifecycle
The connector manager SHALL run at most one adapter task per `(owner_id, platform)` using
that owner's resolved credentials, and report status/heartbeat per owner. Starting all
enabled connectors SHALL start every enabled `(owner_id, platform)` row.

#### Scenario: Concurrent adapters per owner
- **WHEN** owner A and owner B both enable Telegram
- **THEN** two adapter tasks run concurrently, each with its owner's token, and stopping
  one does not affect the other

### Requirement: Owner-isolated inbound routing
Inbound messages SHALL carry the receiving connector's `owner_id`, and routing SHALL use
it for IM-user identity, allowlist checks, agent resolution, and session namespacing so
two owners never share inbound state. For webhook platforms the owner SHALL be resolved
from the destination connector identity (e.g. WhatsApp `phone_number_id`).

#### Scenario: Same platform user under two owners is distinct
- **WHEN** the same platform user messages owner A's bot and owner B's bot
- **THEN** two distinct internal IM-user identities and sessions are used, one per owner

#### Scenario: Unmapped webhook target rejected
- **WHEN** a WhatsApp webhook arrives for a `phone_number_id` not mapped to any owner
- **THEN** the message is rejected and not routed

### Requirement: Owner-scoped IM identity and allowlist
IM user mapping and allowlist entries SHALL be keyed to include `owner_id`. Allowlist
decisions SHALL apply within the owner's scope only.

#### Scenario: Allowlist isolated per owner
- **WHEN** a platform user is allowed under owner A but not owner B
- **THEN** the user can interact with owner A's bot and is rejected by owner B's bot

### Requirement: Admin sees and manages all owners
A caller with admin/superuser role SHALL be able to list, read, and manage connectors and
allowlist entries across all owners, and each returned row SHALL include its `owner_id`. A
non-admin caller SHALL be restricted to their own owner scope regardless of any requested
`owner_id`.

#### Scenario: Admin lists across owners
- **WHEN** an admin lists connectors with the all-owners scope
- **THEN** connectors from every owner are returned, each annotated with its `owner_id`

#### Scenario: Non-admin cannot target another owner
- **WHEN** a non-admin caller requests another owner's connector
- **THEN** the request is denied or silently scoped to the caller's own owner

### Requirement: Admin UI shows owner scope
The IM Connectors admin UI SHALL display the caller's connectors, show an owner column
when an admin views across owners, and attach newly created connectors to the caller's
owner. Secret fields SHALL remain masked and never prefilled.

#### Scenario: Create attaches to caller owner
- **WHEN** an owner creates a connector in the UI
- **THEN** it is persisted under that caller's `owner_id`

### Requirement: Backward-compatible migration to admin owner
Migration SHALL reassign existing global connectors, IM users, and allowlist entries to
the built-in admin owner without data loss, so the current single-tenant deployment keeps
functioning after upgrade.

#### Scenario: Existing global rows migrate to admin owner
- **WHEN** the migration runs against a pre-change database with global connector rows
- **THEN** each row is preserved and reassigned `owner_id` = the admin owner id
