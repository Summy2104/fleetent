# im-user-allowlist Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
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

