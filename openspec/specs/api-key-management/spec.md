# api-key-management Specification

## Purpose
TBD - created by archiving change 2026-05-30-user-management. Update Purpose after archive.
## Requirements
### Requirement: Multiple API keys per user
A user SHALL be able to hold multiple API keys, each with an optional expiry, an agent-level scope allowlist, and a note. Keys SHALL be independently issued, rotated, and revoked without affecting others.

#### Scenario: Issue shows plaintext once
- **WHEN** an admin issues a new key for a user
- **THEN** the plaintext key is shown exactly once and only its hash + prefix are stored

#### Scenario: Independent revoke
- **WHEN** a user holds keys A and B and the admin revokes A
- **THEN** A returns 401 on `/chat` while B continues to work

#### Scenario: Rotate one key
- **WHEN** the admin rotates key A
- **THEN** A's old value is immediately invalid and a new value is issued; other keys are unaffected

### Requirement: Agent-level scope enforcement
Each key MAY carry an agent allowlist (`["*"]` means all). When a `/chat` request routes to a target agent not in the key's scope, the request SHALL be rejected.

#### Scenario: Scope blocks other agent
- **WHEN** key A has scope `["ops-bot"]` and a request with A routes to `support-bot`
- **THEN** the response is 403 ("scope does not allow this agent")

#### Scenario: Scope allows listed agent
- **WHEN** key A has scope `["ops-bot"]` and routes to `ops-bot`, or scope is `["*"]`
- **THEN** the request is allowed

### Requirement: Key validity on authentication
`get_by_api_key` / key resolution SHALL treat a key as invalid when it is revoked, expired, or its owning user is blocked.

#### Scenario: Expired key rejected
- **WHEN** a key past its `expires_at` is used
- **THEN** authentication fails (401)

#### Scenario: Blocked owner rejects key
- **WHEN** a key whose owning user is `blocked` is used
- **THEN** authentication fails (401)

### Requirement: Key usage tracking
The system SHALL record per key: created time, last-used time, last source IP/UA, and cumulative call count.

#### Scenario: Usage updates on call
- **WHEN** a key authenticates a `/chat` call
- **THEN** its `last_used_at`, `last_ip`, `last_ua`, and `call_count` are updated

#### Scenario: List shows usage without plaintext
- **WHEN** an admin lists a user's keys
- **THEN** each entry shows prefix, created/last-used, source IP/UA, call count — never the plaintext

### Requirement: 单轨真相源与明文禁令
`api_keys` 表 SHALL 是 API key 的唯一持久化真相源（单轨制）。系统任何表 MUST NOT 持久化明文 key——key 以 `key_hash` 哈希入库，明文仅在创建时刻返回调用方一次。认证路径 MUST 全部经 `api_keys` 哈希比对，不存在第二条凭证查找路径。

#### Scenario: 全库无明文 key
- **WHEN** 检查管理库 schema 与写入路径
- **THEN** 除创建时一次性返回外，任何表与日志不持久化明文 key（`users` 表无 key 列）

#### Scenario: 认证单路径
- **WHEN** 任一部署形态（managed / standalone）解析 bearer key
- **THEN** 解析均为 `api_keys` 表的哈希比对，无 fallback 第二来源

### Requirement: Expiry reminder and renewal
Keys with an expiry SHALL trigger a renewal reminder N days before expiry and be renewable in one action; they expire on the due date if not renewed.

#### Scenario: Reminder before expiry
- **WHEN** a key with a 30-day expiry reaches the reminder threshold
- **THEN** a renewal reminder email is sent and the key is marked "expiring" in the UI

#### Scenario: One-click renew
- **WHEN** the admin/user renews an expiring key
- **THEN** its `expires_at` is extended and the action is audited

### Requirement: 服务账号创建 HTTP API

平台 SHALL 在 `POST /admin/service-principals` 暴露服务账号创建端点，包装 `user_store.create_user(name)`：创建用户并即时签发一把 `ma-` API key（scope `["*"]`）。明文 key MUST 仅在创建响应中一次性返回（`api_key_plaintext_once`），之后不可再查。端点 MUST 要求 admin 角色并写审计。该端点等价于 CLI `create-user` 的 bootstrap 路径（区别于 `POST /admin/users` 的 web 用户创建——后者需 email、不发 key）。

#### Scenario: 创建服务账号并一次性返回 key

- **WHEN** admin 调用 `POST /admin/service-principals`，body 含 `name`
- **THEN** 系统创建用户、签发 `ma-` key，响应含 `api_key_plaintext_once`（明文，仅此一次）
- **AND** 后续查询该用户的 key 列表不再返回明文

#### Scenario: 与 web 用户创建语义区分

- **WHEN** 对比 `POST /admin/service-principals` 与 `POST /admin/users`
- **THEN** 前者建服务账号即发 key（无需 email），后者建 web 用户（需 email、不发 key）

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用该端点
- **THEN** 系统返回 403

### Requirement: API key revoke and rotate in the React SPA

The React admin SPA SHALL let an admin, for a selected user, list API keys, create a key, **rotate** a key, and **revoke** an individual key — closing the legacy gap where keys could only be created. A newly created or rotated key's plaintext value SHALL be shown once for copy and SHALL NOT be re-displayed or re-fetched afterward; the list SHALL show only a masked prefix.

#### Scenario: Revoke an individual key

- **WHEN** an admin revokes a listed key and confirms
- **THEN** the SPA calls `DELETE /admin/keys/{key_id}` and the key is removed from the list

#### Scenario: Rotate a key shows the new secret once

- **WHEN** an admin rotates a key
- **THEN** the SPA calls `POST /admin/users/{id}/rotate-key`, shows the new plaintext key once for copy, and the list afterward shows only the masked prefix

#### Scenario: Plaintext key is never re-shown

- **WHEN** the key list is re-rendered or re-fetched after creation/rotation
- **THEN** no plaintext key value is displayed; only the masked prefix is shown

### Requirement: 按用户原子轮换 key HTTP API

平台 SHALL 在 `POST /admin/users/{user_id}/rotate-key` 暴露按用户原子轮换端点，包装 `user_store.rotate_key(user_id)`：撤销该用户全部 active key 并签发一把新 key。新 key 明文 MUST 一次性返回。user 不存在 SHALL 返回 404。端点 MUST 要求 admin 角色并写审计。等价于 CLI `rotate-key`。

#### Scenario: 轮换撤销旧 key 并发新 key

- **WHEN** 某用户持有 active key A、B，admin 调用 `POST /admin/users/{user_id}/rotate-key`
- **THEN** A、B 立即失效，系统签发一把新 key，响应含明文（仅此一次）

#### Scenario: 轮换不存在的用户返回 404

- **WHEN** admin 以不存在的 `user_id` 调用
- **THEN** 系统返回 404，不签发任何 key

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用该端点
- **THEN** 系统返回 403

### Requirement: api_keys.user_id 外键完整性
`api_keys.user_id` **MUST** 经外键 `→ users(id) ON DELETE CASCADE` 约束。删除一个 user 时,其名下全部 api_keys 行随之级联删除,不产生 user_id 指向已不存在 user 的孤儿 key。此为结构性完整性,独立于认证期的"owner blocked → 401"运行时校验。

#### Scenario: 删用户级联清 key
- **WHEN** 删除一个名下有若干 api_keys 的 user
- **THEN** 该 user 的全部 api_keys 行随删除级联清除,管理库中不留 user_id 指向该已删 user 的 key 行

#### Scenario: 无孤儿 key 残留
- **WHEN** 对管理库执行完整性审计(api_keys JOIN users)
- **THEN** 不存在 user_id 无法在 users 中匹配的 api_keys 行

