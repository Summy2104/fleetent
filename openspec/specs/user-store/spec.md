# user-store Specification

## Purpose
定义用户存储、legacy API key 读取，以及 agent/runtime 可依赖而不反向触碰 platform 的边界。
## Requirements
### Requirement: Expanded users schema
The `users` table SHALL carry `email`, `password_hash`, `role` (default `viewer`), `status` (default `active`; one of `active`/`disabled`/`blocked`), and `must_reset` (default 0)，schema 由管理库 Alembic 迁移维护（非 store 自建）。`users` 表 SHALL NOT 含 `api_key` 列——API key 唯一真相源为 `api_keys` 表。

#### Scenario: Columns present at head
- **WHEN** 管理库 Alembic 迁移运行到最新版本
- **THEN** `users` has `email`, `password_hash`, `role`, `status`, `must_reset`
- **AND** `users` 不含 `api_key` 列

#### Scenario: Idempotent migration on legacy db
- **WHEN** an older `users` table without these columns is initialized
- **THEN** the columns are added with defaults and existing rows are preserved

#### Scenario: 存量明文 key 经回填迁移
- **WHEN** 含 `users.api_key` 明文值的旧库升级到最新版本
- **THEN** 每个明文 key 以哈希形式回填为 `api_keys` 行（scope `["*"]`、无过期、归属同一 user），随后 `api_key` 列被移除，原 key 仍可用于认证

### Requirement: API keys move to a dedicated table
API keys SHALL be stored exclusively in the `api_keys` table (multiple per user, `key_hash` 哈希入库)。历史 `users.api_key` 单 key 列已退役：存量值由 Alembic 数据迁移哈希回填进 `api_keys`（scope `["*"]`、无过期、幂等）后列被 drop。`create_user` SHALL 直接在 `api_keys` 建 key（明文仅创建时返回一次，MUST NOT 持久化明文）。一次性迁移工具 `platform.user_management.migrate_api_keys()` 使命完成 SHALL 删除；`user_store` MUST NOT import `fleetent.platform.*`。

#### Scenario: Legacy key migrated
- **WHEN** the migration runs on a database with `users.api_key` values
- **THEN** each becomes an `api_keys` row with scope `["*"]`, no `expires_at`, owned by the same user

#### Scenario: Migration entrypoint stays in platform
- **WHEN** the legacy api-key migration function is invoked
- **THEN** it is exposed from `platform.user_management`
- **AND** `user_store` does not provide a migration helper that imports `fleetent.platform.*`

#### Scenario: 新用户的 key 落新轨
- **WHEN** `create_user` 创建用户
- **THEN** `api_keys` 新增一行（哈希），`users` 行不含任何 key 值，明文仅在本次调用返回

#### Scenario: 回填幂等
- **WHEN** 回填迁移在同一旧库上重复运行
- **THEN** 不产生重复 `api_keys` 行，不报错

#### Scenario: 一次性工具退役
- **WHEN** 检查 `platform.user_management`
- **THEN** 不存在 `migrate_api_keys` 入口

### Requirement: Key resolution enforces validity
Resolving a user by API key SHALL succeed only when the key exists, is not revoked, is not expired, and its owning user is not `blocked`. 该解析 SHALL 经基座 `Identity` 端口的适配器暴露（见 `identity-port`）。**解析数据源统一为 `api_keys` 表的哈希比对**：platform 注入的 resolver 与 agent 侧（standalone）适配器读同一张表；agent 侧适配器经 `user_store` 的**本地读函数**完成（与读 `users` 表同级的共享 store 本地查询），MUST NOT `import fleetent.platform.*`。`user_store` 自身 MUST NOT 无条件 import platform 来完成认证。有效性语义（存在/未吊销/未过期/owner 非 blocked 才成功）不变。

#### Scenario: Valid key resolves
- **WHEN** a non-revoked, non-expired key of an active user is presented
- **THEN** the owning `User` is returned

#### Scenario: Revoked/expired/blocked rejected
- **WHEN** the key is revoked, expired, or its user is `blocked`
- **THEN** resolution returns `None` (authentication fails)

#### Scenario: agent 侧解析不依赖 platform
- **WHEN** standalone agent（无 platform 进程）解析 bearer key
- **THEN** 解析经 agent 侧适配器对本地 `api_keys` 表哈希比对完成，全程不 `import fleetent.platform.*`

#### Scenario: legacy 列路径不复存在
- **WHEN** 检查 `user_store` 与 `identity` 源码
- **THEN** 不存在按 `users.api_key` 列查找用户的代码路径

### Requirement: user_store does not depend on platform
`user_store` SHALL NOT import `fleetent.platform.*` anywhere, including function-local lazy imports. IM platform-identity lookup/creation belongs to `platform.im_gateway_management`, not to `user_store`, so the shared user-store module never becomes an agent-to-platform leak point.

#### Scenario: user_store has no platform imports
- **WHEN** the `user_store` module is scanned for imports, including function-local ones
- **THEN** no `fleetent.platform.*` import is present

#### Scenario: standalone bearer path stays off platform
- **WHEN** standalone `fleetent agent run` resolves a bearer token through `user_store`-backed identity logic
- **THEN** the call path does not transitively import `fleetent.platform.*`
