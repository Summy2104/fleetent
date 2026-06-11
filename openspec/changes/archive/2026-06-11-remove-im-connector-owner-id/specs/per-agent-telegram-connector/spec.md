## ADDED Requirements

### Requirement: Connector carries no owner_id and reads no platform table

The Telegram connector path SHALL NOT thread an `owner_id` and SHALL NOT read any platform
management table (notably `users`), mirroring `per-agent-slack-connector` and preserving the
adapter's "no platform dependency" contract. The supervisor's runner signature SHALL be
`(agent_name, config)` — no `owner_id` argument — and `telegram.run` / `create_app` SHALL NOT
accept an `owner_id`. The inbound `NormalizedMessage` SHALL NOT carry an `owner_id` field.
Session identity SHALL be derived without an owner prefix: the routed `session_id` equals
the adapter-derived session id, NOT `f"{owner_id}:{session_id}"`. Chat access remains
enforced by the access gate against `msg.user_id` and the connector `access` block.

#### Scenario: Standalone connector starts without a users table

- **WHEN** `fleetent agent run` starts a Telegram connector in an environment where the
  platform `users` table does not exist
- **THEN** the connection starts, the supervisor never reads a platform table, and no
  `no such table: users` error is logged

#### Scenario: Session id has no owner prefix

- **WHEN** a Telegram message is routed
- **THEN** the session id used for load/save/lock is the adapter-derived id with no
  `<owner>:` prefix
