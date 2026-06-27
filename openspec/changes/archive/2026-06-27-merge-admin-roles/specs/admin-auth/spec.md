## MODIFIED Requirements

### Requirement: Three-tier roles

Users SHALL have a `role` of `admin` or `viewer`. `/admin/*` access SHALL require `role == admin`; write operations SHALL be denied to `viewer`. This `role` replaces the boolean `is_admin`; for compatibility `is_admin` is true iff `role == admin`. The previously-special `built_in_admin` role SHALL NOT exist; the bootstrap-seeded admin is an ordinary `admin`.

#### Scenario: Viewer blocked from write
- **WHEN** a `viewer` calls a write endpoint under `/admin`
- **THEN** the response is 403 and no change is persisted

#### Scenario: Admin allowed
- **WHEN** an `admin` calls `GET /admin/users`
- **THEN** the response is 200

#### Scenario: 无 built_in_admin 角色
- **WHEN** 检查任一用户的 `role`
- **THEN** 取值只可能是 `admin` / `viewer`(或正交的 `service`),不存在 `built_in_admin`

### Requirement: Built-in admin seeding

On startup, if no active `admin` exists, the system SHALL seed a bootstrap admin with a fixed username, a generated temporary password written to the startup log, `must_reset=1`, and `role=admin`. This SHALL also serve as break-glass recovery: if all admins are ever lost, a fresh bootstrap admin is re-seeded on next startup.

#### Scenario: Seed on first boot
- **WHEN** the server starts and no active admin exists
- **THEN** a bootstrap `admin` user is created with `must_reset=1` and the initial password is written to the startup log

#### Scenario: Idempotent seed
- **WHEN** the server starts and at least one active admin already exists
- **THEN** no new admin is created and no password is logged

#### Scenario: Break-glass re-seed
- **WHEN** the server starts and zero active admins exist (e.g. all were removed/blocked)
- **THEN** a bootstrap admin is re-seeded with `must_reset=1`

## ADDED Requirements

### Requirement: Last admin is protected

The system SHALL maintain the invariant that **at least one active `admin` always exists**. Any operation that would reduce the count of `role=admin AND status=active` to zero SHALL be rejected with 403 and persist nothing — this includes demoting, blocking, and deleting an admin, including a user performing the operation on themselves. There is no identity-pinned protected account; protection is purely the count floor. Any admin MAY appoint or remove other admins, subject to this floor. A user MAY always change their own password.

#### Scenario: 降级最后一个 admin 被拒
- **WHEN** 系统中只有一个 active admin,有人尝试把它降级为 viewer
- **THEN** 返回 403,角色不变

#### Scenario: 封禁最后一个 admin 被拒
- **WHEN** 系统中只有一个 active admin,有人尝试封禁(block)它
- **THEN** 返回 403,状态不变(避免锁死全员)

#### Scenario: 删除最后一个 admin 被拒
- **WHEN** 系统中只有一个 active admin,有人尝试删除它
- **THEN** 返回 403,账号不变

#### Scenario: 自我降级/自封最后一个 admin 被拒
- **WHEN** 唯一的 active admin 尝试把自己降级或封禁自己
- **THEN** 返回 403,不变

#### Scenario: 多 admin 时可自由增减与转移
- **WHEN** 存在多个 active admin,某 admin 把另一用户提升为 admin,随后把自己降级为 viewer
- **THEN** 两步均成功(任意时刻仍有 ≥1 active admin),完成权限转移

## REMOVED Requirements

### Requirement: Built-in admin is protected
**Reason**: 身份钉死式保护("内置 admin 这个具体账号不可删/改名/降级/封禁")被"数量下限"保护取代——见新的 `Last admin is protected`。角色 `built_in_admin` 一并退场。
**Migration**: 管理库 `users` 中现存 `role='built_in_admin'` 行经 Alembic forward-only 迁移改写为 `role='admin'`;原"不可降级/封禁内置 admin"的语义改由"不可使 active admin 数降到 0"的 floor 提供,对最后一个 admin 同样形成等价保护。
