## ADDED Requirements

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
