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

