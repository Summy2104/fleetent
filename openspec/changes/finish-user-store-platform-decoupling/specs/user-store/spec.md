## MODIFIED Requirements

### Requirement: API keys move to a dedicated table
API keys SHALL be stored in a separate `api_keys` table (multiple per user) instead of the single `users.api_key` column. A one-time migration SHALL move each existing `users.api_key` into `api_keys` with scope `["*"]` and no expiry。该一次性迁移函数 SHALL 位于 **`platform.user_management`**(它写 platform 拥有的 `api_keys` 表、读 user_store 的 legacy `users.api_key` 列),MUST NOT 由 `user_store` 托管——`user_store` MUST NOT `import fleetent.platform.*`。迁移行为(scope `["*"]`、无 expiry、归属同一 user)不变。

#### Scenario: Legacy key migrated
- **WHEN** the migration runs on a database with `users.api_key` values
- **THEN** each becomes an `api_keys` row with scope `["*"]`, no `expires_at`, owned by the same user

#### Scenario: 迁移函数在 platform 侧
- **WHEN** 审视该一次性 api_key 迁移函数所在模块
- **THEN** 它位于 `platform.user_management`，`user_store` 内不存在 import `fleetent.platform.*` 的迁移函数

## ADDED Requirements

### Requirement: user_store 不依赖 platform
`user_store` 模块 SHALL NOT `import fleetent.platform.*`(顶层或函数内懒加载均不可)。这把 #1 反向依赖的根除从"认证路径"(见 `identity-port`)扩到**整个 `user_store`**:agent 运行时经 `user_store` 不再传递触及 platform。IM 身份→内部 user 的"获取/创建"能力由 platform 侧 `im_gateway_management`(见 `im-user-mapping` / `im-module`)拥有;`user_store` 不再提供委派到 platform 的 wrapper。

#### Scenario: user_store 无 platform import
- **WHEN** 扫描 `user_store` 模块的全部 import(含函数内懒加载)
- **THEN** 不出现任何 `fleetent.platform.*` import

#### Scenario: standalone agent bearer-auth 不触及 platform
- **WHEN** standalone `fleetent agent run`(无 platform)经 bearer 认证、并经 `user_store` 完成身份解析
- **THEN** 调用链不传递 import 到 `fleetent.platform.*`

## REMOVED Requirements

### Requirement: Look up user by platform identity

**Reason**: `user_store.get_or_create_im_user` 是委派到 `platform.im_gateway_management` 的**冗余 wrapper**且全仓无调用方(死码);"IM 平台身份 → 内部 user 的获取/创建"能力已由 platform 侧 `im_gateway_management.get_or_create` 拥有(见 `im-user-mapping` / `im-module`)。保留该 wrapper 会让 `user_store` 传递泄漏 platform。

**Migration**: 需要"平台身份→内部 user"的 platform 侧调用方直接用 `platform.im_gateway_management.get_or_create`;agent 侧 IM 身份走 `identity-port` 的渠道担保解析器(构造 `Principal`，不创建/不查 user_store)。`user_store` 删除 `get_or_create_im_user`。
