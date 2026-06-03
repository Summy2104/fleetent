## REMOVED Requirements

### Requirement: New IM users require approval before access
**Reason**: Default admission flips to allow-by-default; per-user approval is replaced by channel-level admission (see `im-channel-allowlist`).
**Migration**: Existing `im_users` rows keep their current `allowed` value; only newly auto-registered users default to `allowed=True`.

## ADDED Requirements

### Requirement: New IM users are allowed by default
New users auto-registered from IM platforms SHALL be created with `allowed=True`. Channel-level admission is handled by the channel allowlist (see `im-channel-allowlist`), not per-user approval. Existing rows keep their current value during migration.

#### Scenario: Unknown user sends first message
- **WHEN** a message arrives from a platform_user_id not in `im_users`
- **THEN** a new `im_users` row is created with `allowed=True` and the message is routed normally (subject to the channel allowlist)

#### Scenario: Migration preserves existing values
- **WHEN** the default flips and an existing row has `allowed=False`
- **THEN** that row keeps `allowed=False` (only new rows default to allowed)

### Requirement: Batch block/restore and unified identity view
The workbench SHALL support batch block/restore (each audited, sharing a batch id) and SHALL present all IM identities of the same internal User (Slack + Telegram + WhatsApp) merged together.

#### Scenario: Batch block
- **WHEN** an admin selects multiple IM users and batch-blocks them with a reason
- **THEN** all selected become `allowed=False`, each audited individually under one shared batch id

#### Scenario: Merged identities
- **WHEN** an admin views an internal User with Slack + Telegram identities
- **THEN** both IM identities and their statuses are shown together under that User

## MODIFIED Requirements

### Requirement: Admin can block an IM user
Blocking/restoring IM users SHALL be performed in the admin workbench (UI/API) by `admin`/`built_in_admin` only; `viewer` is read-only. Each block/restore requires a reason and is audited. The CLI `block-user` command is deprecated.

#### Scenario: Admin blocks IM user
- **WHEN** an admin blocks IM user `U999` with a reason
- **THEN** `allowed` becomes `False`, the next message gets a rejection and does not enter the agent loop, and the action is audited

#### Scenario: Admin restores IM user
- **WHEN** an admin restores a blocked IM user with a reason
- **THEN** `allowed` becomes `True`, the next message routes normally, and the action is audited

#### Scenario: Viewer cannot block/restore
- **WHEN** a `viewer` attempts to block or restore an IM user
- **THEN** the action is denied (403) and nothing changes

#### Scenario: CLI block-user deprecated
- **WHEN** an operator runs `fleetent-admin block-user --im-user-id <id>`
- **THEN** the command returns a deprecation notice directing to the admin UI and the IM user's status is unchanged
