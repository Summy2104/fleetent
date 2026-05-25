## ADDED Requirements

### Requirement: New IM users require approval before access
New users auto-registered from IM platforms SHALL be created with `allowed=False` and MUST be approved by an admin before they can interact with the agent.

#### Scenario: Unknown user sends first message
- **WHEN** a message arrives from a platform_user_id not in `im_users`
- **THEN** a new `im_users` row is created with `allowed=False`, and the bot replies with a rejection message (e.g., "你还没有权限使用此 bot，请联系管理员审批")

#### Scenario: Pending user sends another message
- **WHEN** a message arrives from a user with `allowed=False`
- **THEN** the system does NOT route the message to the agent pipeline, and the bot replies with the same rejection message

#### Scenario: Approved user sends message
- **WHEN** a message arrives from a user with `allowed=True`
- **THEN** the message is routed normally to the agent pipeline

### Requirement: Admin can list pending (unapproved) users
The admin CLI SHALL provide a `list-pending` command that lists all IM users with `allowed=False`.

#### Scenario: Pending users exist
- **WHEN** admin runs `fleetent-admin list-pending`
- **THEN** a table is printed with columns: `id`, `platform`, `platform_user_id`, `created_at` for all rows with `allowed=False`

#### Scenario: No pending users
- **WHEN** all IM users are approved (or none exist)
- **THEN** the command prints "No pending users."

### Requirement: Admin can approve an IM user
The admin CLI SHALL provide an `approve-user` command to set `allowed=True` for a given IM user.

#### Scenario: Approve by IM user id
- **WHEN** admin runs `fleetent-admin approve-user --im-user-id <id>`
- **THEN** the `im_users` row's `allowed` field is set to `True`

#### Scenario: User not found
- **WHEN** the specified im-user-id does not exist
- **THEN** the command exits with an error: "IM user <id> not found"

### Requirement: Admin can block an IM user
The admin CLI SHALL provide a `block-user` command to set `allowed=False` for a given IM user (revoking access).

#### Scenario: Block by IM user id
- **WHEN** admin runs `fleetent-admin block-user --im-user-id <id>`
- **THEN** the `im_users` row's `allowed` field is set to `False`

#### Scenario: Already blocked user
- **WHEN** the user's `allowed` is already `False`
- **THEN** the command succeeds silently (idempotent)
