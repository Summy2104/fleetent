# im-connector-registry Specification

## Purpose
TBD - created by archiving change 2026-05-30-im-gateway-management. Update Purpose after archive.
## Requirements
### Requirement: Connector registry storage
The system SHALL store one row per IM platform connector in an `im_connectors` table with columns: `id`, `platform` (TEXT UNIQUE — e.g. `slack`/`telegram`/`whatsapp`), `enabled` (INTEGER default 0), `allowlist_enforced` (INTEGER default 0), `config` (TEXT JSON, nullable), `status` (TEXT default `stopped`), `last_heartbeat_at` (TEXT, nullable), `last_error` (TEXT, nullable), `created_at`, `updated_at`.

#### Scenario: Table initialized
- **WHEN** `_init_db()` runs on a fresh database
- **THEN** the `im_connectors` table exists with the columns above

#### Scenario: Platform uniqueness
- **WHEN** a second row with an existing `platform` is inserted
- **THEN** the insert is rejected by the UNIQUE constraint

### Requirement: Connector status reporting
Adapters SHALL report their connection lifecycle to the registry. `status` SHALL be one of `stopped`, `connecting`, `connected`, `disconnected`, `error`, `unconfigured`.

#### Scenario: Report connected
- **WHEN** an adapter calls `im_connector_store.report_status("slack", "connected")`
- **THEN** the `slack` row's `status` becomes `connected` and `updated_at` is refreshed

#### Scenario: Report error carries message
- **WHEN** an adapter calls `report_status("telegram", "error", error="network timeout")`
- **THEN** the `telegram` row's `status` becomes `error` and `last_error` is `"network timeout"`

#### Scenario: Heartbeat refreshes timestamp
- **WHEN** an adapter calls `im_connector_store.heartbeat("slack")` while connected
- **THEN** the `slack` row's `last_heartbeat_at` is updated to the current time, `status` unchanged

### Requirement: Runtime enable and disable
The system SHALL support enabling or disabling a platform connector at runtime without restarting the service. Disabling SHALL disconnect the adapter and stop it from receiving messages.

#### Scenario: Enable starts the connector
- **WHEN** an admin enables a configured `slack` connector
- **THEN** `im_connectors.slack.enabled` becomes 1 and the connector manager starts the Slack adapter (status transitions toward `connecting`/`connected`)

#### Scenario: Disable stops the connector
- **WHEN** an admin disables the `slack` connector
- **THEN** `enabled` becomes 0, the adapter task is cancelled, status becomes `stopped`, and no further Slack messages enter the pipeline

#### Scenario: Enable on boot
- **WHEN** the server starts
- **THEN** the connector manager starts every connector whose `enabled=1`

### Requirement: Unconfigured connectors are not started
A connector whose resolved config has no usable credentials SHALL be marked `unconfigured` and SHALL NOT be started.

#### Scenario: WhatsApp placeholder
- **WHEN** the `whatsapp` connector has no adapter implementation / no credentials and the manager attempts to start it
- **THEN** its status is set to `unconfigured` and no task is started, without raising an error

### Requirement: Connector listing exposes status
The system SHALL expose connector listing showing platform, enabled flag, status, last heartbeat, last error, and `allowlist_enforced`, with credential values masked.

#### Scenario: List connectors
- **WHEN** an admin requests the connector list
- **THEN** each platform's `platform`, `enabled`, `status`, `last_heartbeat_at`, `last_error`, `allowlist_enforced` are returned and any credential fields are masked

### Requirement: Create a connector for a not-yet-configured platform
The system SHALL allow an admin to create (initialize) a connector row for a platform that has no existing row, supplying its credential config in the same call. Creation SHALL be idempotent: creating for an existing platform SHALL update that platform's config rather than insert a duplicate (the `platform` UNIQUE constraint is preserved). Creation SHALL be admin-only.

#### Scenario: Create a brand-new platform connection
- **WHEN** an admin POSTs a `whatsapp` connector with a credential config and no `whatsapp` row exists
- **THEN** an `im_connectors` row for `whatsapp` is created with that config and the masked connector is returned

#### Scenario: Create for an existing platform updates config
- **WHEN** an admin POSTs a `slack` connector config while a `slack` row already exists
- **THEN** the existing row's config is updated (no duplicate row) and the UNIQUE(platform) constraint is not violated

#### Scenario: Non-admin cannot create a connector
- **WHEN** a viewer attempts to create a connector
- **THEN** the request is rejected with 403 and no row is written

