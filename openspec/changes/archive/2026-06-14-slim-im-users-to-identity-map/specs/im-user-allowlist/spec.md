# im-user-allowlist Delta

## REMOVED Requirements

### Requirement: Admin can list pending (unapproved) users
**Reason**: `allowed`-based per-IM approval 移除——访问由 `user_agents`（agent 授权，默认关）决定，无"pending IM 用户"概念；"授权某人用某 agent" = user-bind（agent-admin-api 已有）。

### Requirement: Admin can approve an IM user
**Reason**: 同上，approve = user-bind 授权，不再是 `im_users.allowed=1`。

### Requirement: New IM users are allowed by default
**Reason**: `allowed` 列删除。新 IM 用户身份照建，但访问默认关（user_agents 空→用不了任何 agent，阶段 3 已落地）——默认行为由访问模型而非 allowed 决定。

## MODIFIED Requirements

### Requirement: Admin can block an IM user
Blocking/restoring a user SHALL be performed in the admin workbench (UI/API) by `admin`/`built_in_admin` only; `viewer` is read-only. Block/restore SHALL operate on **`users.status`**（封整个内部 User），requires a reason, and is audited. Enforcement is at the platform IM resolver (`users.status == "blocked"` → reject); the deprecated `im_users.allowed` flag is removed. The CLI `block-user` command stays deprecated.

#### Scenario: Admin blocks a user
- **WHEN** an admin blocks user `U999` with a reason
- **THEN** `users.status` becomes `blocked`, the next IM message from that user is rejected at the resolver and does not enter the agent loop, and the action is audited

#### Scenario: Admin restores a user
- **WHEN** an admin restores a blocked user with a reason
- **THEN** `users.status` becomes `active`, the next message routes normally, and the action is audited

#### Scenario: Viewer cannot block/restore
- **WHEN** a `viewer` attempts to block or restore
- **THEN** the action is denied (403) and nothing changes

### Requirement: Batch block/restore and unified identity view
The admin workbench SHALL provide a unified IM identity view (listing `im_users` mappings with their internal `user_id`) and batch block/restore operating on `users.status`. The identity view is read-only listing; batch block/restore are `admin`-gated and audited.

#### Scenario: Unified identity view lists mappings
- **WHEN** an admin opens the IM identity view
- **THEN** it lists `(platform, platform_user_id) → user_id` mappings from `im_users`

#### Scenario: Batch block operates on users.status
- **WHEN** an admin batch-blocks several users
- **THEN** each target's `users.status` becomes `blocked` and the actions are audited
