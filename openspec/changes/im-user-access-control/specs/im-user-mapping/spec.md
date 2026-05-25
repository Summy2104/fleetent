## MODIFIED Requirements

### Requirement: Map platform user to internal user
The system SHALL map `(platform, platform_user_id)` to an internal `user_id` before routing to the agent pipeline. New users SHALL be auto-registered with `allowed=False` and SHALL NOT be routed to the agent until approved.

#### Scenario: Known user — allowed
- **WHEN** a Slack message arrives from `platform_user_id=U123` (in `im_users` with `allowed=True`)
- **THEN** `im_user_store.get_or_create("slack", "U123")` returns the corresponding internal `user_id` and `allowed=True`

#### Scenario: Unknown user — first interaction
- **WHEN** a message arrives from a `platform_user_id` not in `im_users`
- **THEN** a new `im_users` row is created with `allowed=False`, and `get_or_create` returns the new `user_id` and `allowed=False`

#### Scenario: Known user — not allowed
- **WHEN** a message arrives from a user with `allowed=False`
- **THEN** `get_or_create` returns the existing `user_id` and `allowed=False`; the caller (normalizer) rejects the request

### Requirement: Platform uniqueness
The `(platform, platform_user_id)` pair SHALL be unique in `im_users`.

#### Scenario: Same Slack user sends multiple messages
- **WHEN** the same `U123` sends a second message
- **THEN** `im_users` still has exactly one row for `("slack", "U123")`, returning the same `user_id`

### Requirement: Schema
The `im_users` table SHALL store: `id`, `platform`, `platform_user_id`, `user_id`, `allowed` (BOOLEAN DEFAULT FALSE), `created_at`, with a UNIQUE constraint on `(platform, platform_user_id)`.

#### Scenario: New user row has allowed=False
- **WHEN** a new `im_users` row is inserted
- **THEN** the `allowed` column defaults to `False`

#### Scenario: Duplicate insert rejected
- **WHEN** code attempts to insert a duplicate `(platform, platform_user_id)`
- **THEN** the database constraint prevents it (use INSERT OR IGNORE or equivalent)
