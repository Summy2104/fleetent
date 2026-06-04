## MODIFIED Requirements

### Requirement: Per-platform credential field schema
The system SHALL define, per **owner-level** platform, the set of credential keys
required to connect to that platform. The schema SHALL be:
- `telegram`: `bot_token`
- `whatsapp`: `phone_number_id`, `access_token`, `verify_token`, `business_account_id`

Slack is no longer an owner-level connector: its credentials are declared per agent via
`connectors.slack` environment references (see `per-agent-slack-connector`) and SHALL
NOT appear in this owner-level schema. These keys drive `.env` fallback resolution and
the admin UI's dynamic credential form for the owner-level platforms only.

#### Scenario: Slack absent from the owner-level schema
- **WHEN** the owner-level connector config schema is read
- **THEN** it lists `telegram` and `whatsapp` but not `slack`

#### Scenario: Telegram credential keys
- **WHEN** the config schema for `telegram` is read
- **THEN** it lists `bot_token`

#### Scenario: WhatsApp credential keys are defined
- **WHEN** the config schema for `whatsapp` is read
- **THEN** it lists `phone_number_id`, `access_token`, `verify_token`, and `business_account_id`

### Requirement: Seed connectors from environment
The system SHALL provide a one-time `seed-connectors` operation that populates
`im_connectors.config` from existing `.env` credentials and sets `enabled=1` for
**owner-level** platforms that have credentials. Slack SHALL be excluded — it is
per-agent and is not seeded from owner-level `.env`.

#### Scenario: Seed excludes Slack
- **WHEN** `seed-connectors` runs and `.env` has `telegram_bot_token`
- **THEN** the `telegram` row is populated and `enabled=1`, and no `slack` row is seeded

#### Scenario: Seed is idempotent
- **WHEN** `seed-connectors` runs again on a platform that already has DB config
- **THEN** that platform is skipped (not overwritten) unless `--force` is given
