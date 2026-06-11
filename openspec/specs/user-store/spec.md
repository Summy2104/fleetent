# user-store Specification

## Purpose
定义用户存储、legacy API key 读取，以及 agent/runtime 可依赖而不反向触碰 platform 的边界。
## Requirements
### Requirement: Expanded users schema
The `users` table SHALL carry `email`, `password_hash`, `role` (default `viewer`), `status` (default `active`; one of `active`/`disabled`/`blocked`), and `must_reset` (default 0). Adding these columns to an existing database SHALL be idempotent and non-destructive.

#### Scenario: Columns present after init
- **WHEN** `_init_db()` runs
- **THEN** `users` has `email`, `password_hash`, `role`, `status`, `must_reset`

#### Scenario: Idempotent migration on legacy db
- **WHEN** an older `users` table without these columns is initialized
- **THEN** the columns are added with defaults and existing rows are preserved

### Requirement: API keys move to a dedicated table
API keys SHALL be stored in a separate `api_keys` table (multiple per user) instead of the single `users.api_key` column. A one-time migration SHALL move each existing `users.api_key` into `api_keys` with scope `["*"]` and no expiry. That migration SHALL live in `platform.user_management`, because it writes the platform-owned `api_keys` table while reading the legacy `users.api_key` column through `user_store`; `user_store` itself MUST NOT import `fleetent.platform.*` to host this migration.

#### Scenario: Legacy key migrated
- **WHEN** the migration runs on a database with `users.api_key` values
- **THEN** each becomes an `api_keys` row with scope `["*"]`, no `expires_at`, owned by the same user

#### Scenario: Migration entrypoint stays in platform
- **WHEN** the legacy api-key migration function is invoked
- **THEN** it is exposed from `platform.user_management`
- **AND** `user_store` does not provide a migration helper that imports `fleetent.platform.*`

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

### Requirement: user_store does not depend on platform
`user_store` SHALL NOT import `fleetent.platform.*` anywhere, including function-local lazy imports. IM platform-identity lookup/creation belongs to `platform.im_gateway_management`, not to `user_store`, so the shared user-store module never becomes an agent-to-platform leak point.

#### Scenario: user_store has no platform imports
- **WHEN** the `user_store` module is scanned for imports, including function-local ones
- **THEN** no `fleetent.platform.*` import is present

#### Scenario: standalone bearer path stays off platform
- **WHEN** standalone `fleetent agent run` resolves a bearer token through `user_store`-backed identity logic
- **THEN** the call path does not transitively import `fleetent.platform.*`
