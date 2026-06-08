## ADDED Requirements

### Requirement: Channel listing grants implicit user access

When a channel is explicitly listed in `access.allow_channels`, the agent SHALL allow all
users in that channel without requiring them to appear in `allow_users` or be locally
approved. The user gate SHALL be skipped for messages from explicitly listed channels.

When `allow_channels` is empty (allow-all-channels mode), no implicit user grant applies
and the user gate remains active.

#### Scenario: User in listed channel bypasses user gate

- **WHEN** `access.allow_channels: ["C1"]` and a message arrives from channel `C1` from
  a user not in `allow_users` and not locally approved
- **THEN** the message proceeds to the agent loop without rejection

#### Scenario: User in unlisted channel still requires authorization

- **WHEN** `access.allow_channels: ["C1"]` and a message arrives from channel `C2` from
  a user not in `allow_users`
- **THEN** the message is rejected (channel gate blocks it first)

#### Scenario: Empty allow_channels does not grant implicit channel access

- **WHEN** `access.allow_channels: []` (empty) and a message arrives from any channel
  from a user not in `allow_users` and not locally approved
- **THEN** the user gate is active and the message is rejected

### Requirement: allow_all_users flag opens access to all users

`ConnectorAccess` SHALL support an `allow_all_users: bool` field (default `false`). When
`true`, the user gate SHALL be skipped for all messages on this connector, including DMs.
`allow_users` entries and the local approval store are still valid but not consulted when
`allow_all_users` is set.

#### Scenario: allow_all_users true allows unknown DM user

- **WHEN** `access.allow_all_users: true` and a DM arrives from a user not in
  `allow_users` and not locally approved
- **THEN** the message proceeds to the agent loop without rejection

#### Scenario: allow_all_users false preserves existing gate behavior

- **WHEN** `access.allow_all_users: false` (default) and a user not in `allow_users`
  sends a message
- **THEN** the existing user gate applies (reject + add to pending if require_approval)

#### Scenario: allow_all_users default is false

- **WHEN** an agent declares a connector with no `allow_all_users` field
- **THEN** `allow_all_users` defaults to `false` and the user gate is active
