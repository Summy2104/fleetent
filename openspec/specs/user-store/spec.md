# user-store Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
### Requirement: Look up user by platform identity
The user_store module SHALL provide a function to look up or create an internal user by platform identity.

#### Scenario: Existing platform user
- **WHEN** `user_store.get_or_create_im_user("slack", "U123")` is called and a matching row exists in `im_users`
- **THEN** the function returns the associated internal `User` object without creating new rows

#### Scenario: New platform user
- **WHEN** `user_store.get_or_create_im_user("slack", "U999")` is called and no matching row exists
- **THEN** a new `User` is created in `users`, a new row is inserted in `im_users`, and the `User` is returned

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
Resolving a user by API key SHALL succeed only when the key exists, is not revoked, is not expired, and its owning user is not `blocked`. 该解析 SHALL 经基座 `Identity` 端口的适配器暴露（见 `identity-port`）；**agent 侧（standalone）解析适配器 MUST NOT `import fleetent.platform.*`**——platform 专属的 `api_keys` 表解析仅存在于 platform 侧适配器。`user_store` 自身 MUST NOT 无条件 import platform 来完成认证（根除 #1 泄漏）。有效性语义（存在/未吊销/未过期/owner 非 blocked 才成功）不变。

#### Scenario: Valid key resolves
- **WHEN** a non-revoked, non-expired key of an active user is presented
- **THEN** the owning `User` is returned

#### Scenario: Revoked/expired/blocked rejected
- **WHEN** the key is revoked, expired, or its user is `blocked`
- **THEN** resolution returns `None` (authentication fails)

#### Scenario: agent 侧解析不依赖 platform
- **WHEN** standalone agent（无 platform、platform 表不存在）解析 bearer key
- **THEN** 解析经 agent 侧适配器完成，全程不 `import fleetent.platform.*`、不查询 platform 表

