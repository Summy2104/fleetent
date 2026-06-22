## Purpose

Maps IM platform users `(platform, platform_user_id)` to internal user records, creating new records on first contact and maintaining uniqueness per platform identity.
## Requirements
### Requirement: Map platform user to internal user
The system SHALL map `(platform, platform_user_id)` to an internal `user_id` before routing to the agent pipeline **when an identity resolver has been injected**. In managed deployments the platform injects the resolver at startup via `im_gateway.access.set_im_identity_resolver`; the resolver is platform-owned and may write platform identity tables, while the agent module MUST NOT know its implementation or schema. Without resolver injection (standalone), `resolve_identity` SHALL return the native `platform_user_id` unchanged.

On first contact provisioning SHALL go through an **email-keyed resolution** (`resolve_or_provision`) when a **verified email** is available for the channel identity: it SHALL look up an existing user by `(edge_tenant, normalized_email)` and, if found, **link** the channel identity to that existing user (write the `im_users` mapping); if not found, create a new email-keyed user in the edge tenant and link it. When **no verified email** is available, provisioning SHALL fall back to creating a channel-keyed user in the **connector edge tenant** (`create_user(tenant_id=edge_tenant)`, edge_tenant = the receiving bot's `agent.tenant_id`).

Linking SHALL be **attach-only, never merge**: it only attaches a channel identity that has **no existing user mapping** to an email-keyed user. The system MUST NOT auto-merge two already-existing internal users (e.g., a channel identity already mapped to user A whose verified email matches user B) — such cases are left to manual/admin resolution.

#### Scenario: Known user (managed)
- **WHEN** a Slack message arrives from `platform_user_id=U123` (already in `im_users`) and the resolver is injected
- **THEN** the resolver returns the corresponding internal `user_id`, used as `Principal.user_id`

#### Scenario: Unknown user, verified email links to existing user (managed)
- **WHEN** a message arrives from a `platform_user_id` not in `im_users`, a verified email is available, and a user with that `(edge_tenant, normalized_email)` already exists
- **THEN** the channel identity is **linked** to that existing user (new `im_users` row → existing `user_id`); no new user is created

#### Scenario: Unknown user, verified email, no existing user (managed)
- **WHEN** a message arrives from an unmapped `platform_user_id` with a verified email and no matching user exists
- **THEN** a new email-keyed user is created in the edge tenant and the channel identity is mapped to it

#### Scenario: Unknown user, no verified email (managed)
- **WHEN** a message arrives from an unmapped `platform_user_id` and no verified email is available
- **THEN** a new channel-keyed user is created in the edge tenant and mapped (current behavior; cross-channel unification deferred to manual `/link`)

#### Scenario: No auto-merge of pre-existing users
- **WHEN** a channel identity already mapped to user A presents a verified email matching a different existing user B
- **THEN** the system MUST NOT merge A and B automatically; the existing mapping is unchanged and the case is surfaced for manual resolution

#### Scenario: Same person converges across IM and bearer (managed)
- **WHEN** the same human first talks over IM and later calls with that mapped user's bearer key (or reverse)
- **THEN** both paths resolve to the same `Principal.user_id`; agent-side memory/session converge

#### Scenario: Standalone passthrough
- **WHEN** an IM message arrives with no resolver injected
- **THEN** `resolve_identity` returns the native `platform_user_id`, no platform table read

#### Scenario: Blocked user rejected (managed)
- **WHEN** the resolver maps a channel identity to a user whose `users.status == "blocked"`
- **THEN** the message is rejected (blocking is enforced at the platform resolver via `users.status`)

#### Scenario: Tenant mismatch is rejected (managed)
- **WHEN** the mapped user's `tenant_id` differs from the connector edge tenant
- **THEN** the message is rejected and a diagnostic log entry is recorded

### Requirement: Platform uniqueness
`(platform, platform_user_id)` SHALL map to exactly one `im_users` row globally — one internal `user_id` per IM platform identity. （移除 per-`owner_id` 分行 + 跨 owner 复用语义：`owner_id` 列删除，身份不再按 owner/agent 分作用域。）

#### Scenario: Same platform user sends multiple messages
- **WHEN** the same `U123` sends repeated Slack messages
- **THEN** `im_users` has exactly one row for `("slack", "U123")`, returning the same `user_id`

#### Scenario: Same platform user seen by two bots
- **WHEN** two different agent bots both receive messages from platform user `U123`
- **THEN** `im_users` still has exactly one row for `("slack", "U123")` and both resolve to the same internal `user_id`

### Requirement: Schema
The `im_users` table SHALL store: `id`, `platform`, `platform_user_id`, `user_id`, `created_at`, `meta_json`, with a UNIQUE constraint on `(platform, platform_user_id)` and a FK `user_id`→`users.id` ON DELETE CASCADE. It SHALL NOT carry `owner_id` or `allowed` (identity-only table; access via `user_agents`, blocking via `users.status`).

#### Scenario: Duplicate insert rejected
- **WHEN** code attempts to insert a duplicate `(platform, platform_user_id)`
- **THEN** the database constraint prevents it (INSERT OR IGNORE or equivalent)

#### Scenario: No owner_id / allowed columns
- **WHEN** inspecting the `im_users` schema at head
- **THEN** there are no `owner_id` or `allowed` columns; `user_id` has a FK to `users.id`

### Requirement: im_users schema 权威为 Alembic
`im_users` 表 SHALL 仅由管理库 Alembic 迁移建立与演进（双权威契约：管理表 Alembic-only）。`platform/im_gateway_management/identity.py` SHALL NOT 在运行时自建表（不得含 `CREATE TABLE` / `_init_db` 路径），SHALL NOT re-export `user_store.DB_PATH`，SQL MUST 使用 named parameters（不得使用 `?` 占位符）。`im_user_store` 兼容 shim SHALL NOT re-export `_init_db`。

#### Scenario: store 不再自建表
- **WHEN** 检查 `platform/im_gateway_management/identity.py` 源码
- **THEN** 模块内不存在 `CREATE TABLE` 语句、`_init_db` 函数与 `DB_PATH` re-export，所有 SQL 使用 named parameters

#### Scenario: 热路径解析不跑建表检查
- **WHEN** managed 模式下注入的身份 resolver 处理一条 IM 消息（调用 `get_or_create`）
- **THEN** 解析路径不执行任何 `CREATE TABLE` / schema 检查语句

#### Scenario: 行为不变
- **WHEN** 经 Alembic 建好 schema 的管理库上调用 `get_or_create` / `approve_user` / `block_user` / `list_*`
- **THEN** 各函数行为与签名与清理前一致

#### Scenario: shim 导出面缩减
- **WHEN** 检查 `fleetent.im_user_store` shim
- **THEN** 不再 re-export `_init_db`；其余既有 re-export 保持

