# im-connector-config Specification

## Purpose
TBD - created by archiving change 2026-05-30-im-gateway-management. Update Purpose after archive.
## Requirements
### Requirement: Config resolution with .env fallback
The system SHALL resolve a connector's credentials by reading `im_connectors.config` (JSON) first, and falling back to the corresponding `.env` settings when the DB config is empty.

#### Scenario: DB config present
- **WHEN** `im_connectors.slack.config` contains `{"bot_token": "xoxb-db", "app_token": "xapp-db"}`
- **THEN** `im_connector_config.resolve("slack")` returns those DB values

#### Scenario: DB config empty falls back to .env
- **WHEN** `im_connectors.slack.config` is NULL and `.env` has `slack_bot_token`
- **THEN** `resolve("slack")` returns the `.env` value

### Requirement: Masked read for management surfaces
The system SHALL provide a masked view of connector config where credential fields show only the last 4 characters. Raw credentials SHALL only be used internally by adapters.

#### Scenario: Masked resolve
- **WHEN** an admin reads the `slack` connector config via API/CLI
- **THEN** a token like `xoxb-1234567890abcd` is returned as a masked form exposing only `abcd` (e.g. `xoxb-****abcd`)

#### Scenario: Adapter uses raw value
- **WHEN** the Slack adapter starts
- **THEN** it obtains the unmasked token via `resolve("slack")`, not the masked view

### Requirement: Update connector config
The system SHALL allow updating a connector's config via admin API/CLI; updating config SHALL mark the connector for reload.

#### Scenario: Update token
- **WHEN** an admin sets a new bot token for `telegram`
- **THEN** `im_connectors.telegram.config` is updated and a reload of the running connector is triggered (or takes effect on next start)

### Requirement: Seed connectors from environment
The system SHALL provide a one-time `seed-connectors` operation that populates `im_connectors.config` from existing `.env` credentials and sets `enabled=1` for platforms that have credentials.

#### Scenario: Seed from .env
- **WHEN** `seed-connectors` runs and `.env` has `slack_bot_token` + `slack_app_token` but no `telegram_bot_token`
- **THEN** the `slack` row gets its config populated and `enabled=1`, while `telegram` remains `unconfigured`/`enabled=0`

#### Scenario: Seed is idempotent
- **WHEN** `seed-connectors` runs again on a platform that already has DB config
- **THEN** that platform is skipped (not overwritten) unless `--force` is given

### Requirement: Per-platform credential field schema
The system SHALL define, per platform, the set of credential keys required to connect to that platform. The schema SHALL be:
- `telegram`: `bot_token`
- `slack`: `bot_token` (xoxb bot token), `signing_secret`, `app_token` (xapp socket-mode token)
- `whatsapp`: `phone_number_id`, `access_token`, `verify_token`, `business_account_id`

These keys SHALL drive both `.env` fallback resolution and the admin UI's dynamic credential form.

#### Scenario: Slack credential keys include signing secret and app token
- **WHEN** the config schema for `slack` is read
- **THEN** it lists `bot_token`, `signing_secret`, and `app_token`

#### Scenario: WhatsApp credential keys are defined
- **WHEN** the config schema for `whatsapp` is read
- **THEN** it lists `phone_number_id`, `access_token`, `verify_token`, and `business_account_id`

#### Scenario: Telegram credential keys
- **WHEN** the config schema for `telegram` is read
- **THEN** it lists `bot_token`

### Requirement: Mask all configured credential fields
The masked read SHALL mask every value present in a platform's stored config, regardless of which platform-specific keys are set, exposing only the last 4 characters.

#### Scenario: WhatsApp access token masked
- **WHEN** an admin reads the `whatsapp` connector config and `access_token` is `EAAG1234567890wxyz`
- **THEN** the returned `access_token` is masked exposing only `wxyz` (e.g. `****wxyz`)

