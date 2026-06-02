## ADDED Requirements

### Requirement: Expanded users schema
The `users` table SHALL carry `email`, `password_hash`, `role` (default `viewer`), `status` (default `active`; one of `active`/`disabled`/`blocked`), and `must_reset` (default 0). Adding these columns to an existing database SHALL be idempotent and non-destructive.

#### Scenario: Columns present after init
- **WHEN** `_init_db()` runs
- **THEN** `users` has `email`, `password_hash`, `role`, `status`, `must_reset`

#### Scenario: Idempotent migration on legacy db
- **WHEN** an older `users` table without these columns is initialized
- **THEN** the columns are added with defaults and existing rows are preserved

### Requirement: API keys move to a dedicated table
API keys SHALL be stored in a separate `api_keys` table (multiple per user) instead of the single `users.api_key` column. A one-time migration SHALL move each existing `users.api_key` into `api_keys` with scope `["*"]` and no expiry.

#### Scenario: Legacy key migrated
- **WHEN** the migration runs on a database with `users.api_key` values
- **THEN** each becomes an `api_keys` row with scope `["*"]`, no `expires_at`, owned by the same user

### Requirement: Key resolution enforces validity
Resolving a user by API key SHALL succeed only when the key exists, is not revoked, is not expired, and its owning user is not `blocked`.

#### Scenario: Valid key resolves
- **WHEN** a non-revoked, non-expired key of an active user is presented
- **THEN** the owning `User` is returned

#### Scenario: Revoked/expired/blocked rejected
- **WHEN** the key is revoked, expired, or its user is `blocked`
- **THEN** resolution returns `None` (authentication fails)
