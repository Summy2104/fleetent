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
