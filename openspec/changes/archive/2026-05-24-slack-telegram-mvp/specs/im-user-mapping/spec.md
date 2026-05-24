## ADDED Requirements

### Requirement: Map platform user to internal user
The system SHALL map `(platform, platform_user_id)` to an internal `user_id` before routing to the agent pipeline.

#### Scenario: Known user
- **WHEN** a Slack message arrives from `platform_user_id=U123` (already in `im_users` table)
- **THEN** `im_user_store.get_user_id("slack", "U123")` returns the corresponding internal `user_id`

#### Scenario: Unknown user — first interaction
- **WHEN** a message arrives from a `platform_user_id` not in `im_users`
- **THEN** a new `im_users` row is created with a new internal `user_id`, and that `user_id` is used for this message

### Requirement: Platform uniqueness
The `(platform, platform_user_id)` pair SHALL be unique in `im_users`.

#### Scenario: Same Slack user sends multiple messages
- **WHEN** the same `U123` sends a second message
- **THEN** `im_users` still has exactly one row for `("slack", "U123")`, returning the same `user_id`

### Requirement: Schema
The `im_users` table SHALL store: `id`, `platform`, `platform_user_id`, `user_id`, `created_at`, with a UNIQUE constraint on `(platform, platform_user_id)`.

#### Scenario: Duplicate insert rejected
- **WHEN** code attempts to insert a duplicate `(platform, platform_user_id)`
- **THEN** the database constraint prevents it (use INSERT OR IGNORE or equivalent)
