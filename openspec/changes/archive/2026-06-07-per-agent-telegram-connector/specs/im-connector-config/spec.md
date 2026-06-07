## MODIFIED Requirements

### Requirement: Seed connectors from environment
The system SHALL provide a one-time `seed-connectors` operation that populates
`im_connectors.config` from existing `.env` credentials and sets `enabled=1` for
**owner-level** platforms that have credentials. Slack AND Telegram SHALL be excluded —
they are per-agent and are not seeded from owner-level `.env`.

#### Scenario: Seed excludes per-agent platforms
- **WHEN** `seed-connectors` runs and `.env` has `whatsapp_access_token`
- **THEN** the `whatsapp` row is populated and `enabled=1`, and no `slack` or `telegram` row is seeded

#### Scenario: Seed is idempotent
- **WHEN** `seed-connectors` runs again on a platform that already has DB config
- **THEN** that platform is skipped (not overwritten) unless `--force` is given

### Requirement: Per-platform credential field schema
The system SHALL define, per **owner-level** platform, the set of credential keys
required to connect to that platform. The schema SHALL be:
- `whatsapp`: `phone_number_id`, `access_token`, `verify_token`, `business_account_id`

Slack and Telegram are no longer owner-level connectors: their credentials are declared per
agent via `connectors.slack` / `connectors.telegram` environment references (see
`per-agent-slack-connector` and `per-agent-telegram-connector`) and SHALL NOT appear in this
owner-level schema. These keys drive `.env` fallback resolution and the admin UI's dynamic
credential form for the owner-level platforms only.

#### Scenario: Per-agent platforms absent from the owner-level schema
- **WHEN** the owner-level connector config schema is read
- **THEN** it lists `whatsapp` but not `slack` or `telegram`

#### Scenario: WhatsApp credential keys are defined
- **WHEN** the config schema for `whatsapp` is read
- **THEN** it lists `phone_number_id`, `access_token`, `verify_token`, and `business_account_id`
