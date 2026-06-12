# user-blocklist Specification

## Purpose
TBD - created by archiving change 2026-05-30-user-management. Update Purpose after archive.
## Requirements
### Requirement: One-click cascade block
Blocking a user (reason required) SHALL set `status=blocked`, revoke all the user's API keys, disable all associated IM accounts, add the email (and OAuth subject if any) to a no-registration list, and write an audit entry.

#### Scenario: Cascade takes effect
- **WHEN** an admin blocks a user holding 2 keys and bound Slack + Telegram, with a reason
- **THEN** both keys are revoked, both IM accounts are disabled, the email is added to the no-registration list, and an audit entry is written

#### Scenario: Blocked key rejected
- **WHEN** a key of a blocked user is used on `/chat`
- **THEN** the response is 401

#### Scenario: Re-registration blocked
- **WHEN** an account creation uses an email on the no-registration list
- **THEN** the operation is rejected

### Requirement: Unblock does not revive keys
Unblocking SHALL restore login but SHALL NOT auto-restore previously revoked keys; IM accounts require re-approval.

#### Scenario: Unblock restores login only
- **WHEN** an admin unblocks a user
- **THEN** `status` becomes `active`, previously revoked keys stay invalid, and IM accounts must be re-approved

### Requirement: Batch block
The system SHALL support batch-blocking by email domain, IP, or registration time window, auditing each with a shared batch id.

#### Scenario: Batch by email domain
- **WHEN** an admin batch-blocks `email domain = evil.com`
- **THEN** all matching accounts are blocked and recorded with one shared batch id in the audit log


### Requirement: 封禁职责按层拆分
封禁能力 SHALL 按层拆分归属，行为不变：admin 级联编排（设置 status、吊销 API 密钥、禁用 IM 账号、写注册封禁、写审计）SHALL 由 platform 层拥有；注册封禁存储（记录与查询被禁止重新注册的 email）SHALL 由 governance 拥有且 agent 侧可读，不依赖 platform。

#### Scenario: 级联编排由 platform 提供
- **WHEN** admin 接口触发封禁/解封/批量封禁
- **THEN** 调用 platform 层的 block service，由它协调用户状态、密钥吊销、IM 禁用、注册封禁与审计

#### Scenario: 注册封禁查询 agent 可读
- **WHEN** agent 侧 user_store 在创建用户时校验 email 是否被禁止重新注册
- **THEN** 它调用 governance 的注册封禁查询，且该路径不 import platform

### Requirement: 注册封禁表的 schema 权威为 Alembic
`blocked_registrations` 表 SHALL 仅由管理库 Alembic 迁移建立与演进（双权威契约：
管理表 Alembic-only）。`governance/blocklist.py` SHALL NOT 在运行时自建表，
SHALL NOT re-export `user_store.DB_PATH`，SQL MUST 使用 named parameters。
收编迁移 MUST 幂等承接存量部署中 store 既建的同构表（表已存在时不报错、不丢数据）。

#### Scenario: Alembic 建表
- **WHEN** 管理库 Alembic 迁移运行到最新版本（全新库）
- **THEN** `blocked_registrations` 表存在，含 email、reason、batch_id 与创建时间字段

#### Scenario: 存量自建表被幂等承接
- **WHEN** 存量部署的管理库中已有 store 自建的 `blocked_registrations` 表，运行收编迁移
- **THEN** 迁移成功且既有封禁行保留

#### Scenario: store 不再自建表
- **WHEN** 检查 `governance/blocklist.py` 源码
- **THEN** 模块内不存在 `CREATE TABLE` 语句与 `DB_PATH` re-export，所有 SQL 使用 named parameters

#### Scenario: 封禁行为不变
- **WHEN** platform block service 写入封禁、user_store 注册路径查询封禁
- **THEN** `ban_registration` / `is_registration_blocked` 行为与签名与收编前一致
