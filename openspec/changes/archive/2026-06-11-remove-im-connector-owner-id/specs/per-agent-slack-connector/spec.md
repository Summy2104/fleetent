## ADDED Requirements

### Requirement: Connector carries no owner_id and reads no platform table

The Slack connector path SHALL NOT thread an `owner_id` and SHALL NOT read any platform
management table (notably `users`). The supervisor's runner signature SHALL be
`(agent_name, config)` — no `owner_id` argument — and `slack.run` / `create_app` SHALL NOT
accept an `owner_id`. The inbound `NormalizedMessage` SHALL NOT carry an `owner_id` field.
Session identity SHALL be derived without an owner prefix: the routed `session_id` equals
the adapter-derived session id (`channel_type` + `channel_id` + `user_id` + `thread_root`),
NOT `f"{owner_id}:{session_id}"`. User and channel access remain enforced by the normalizer
access gate against `msg.user_id` and the connector `access` block, independent of any owner.

#### Scenario: Standalone connector starts without a users table

- **WHEN** `fleetent agent run` starts a Slack connector in an environment where the
  platform `users` table does not exist (no `management.db` / no platform boot)
- **THEN** the connection starts, the supervisor never reads a platform table, and no
  `no such table: users` error is logged

#### Scenario: Adapter stamps agent and user but not owner

- **WHEN** the Slack handler normalizes an inbound message on agent `support`'s connection
- **THEN** the routed `NormalizedMessage` carries `agent_name="support"` and the sender's
  `user_id`, and has no `owner_id`

#### Scenario: Session id has no owner prefix

- **WHEN** a Slack DM from user `U123` is routed
- **THEN** the session id used for load/save/lock is the adapter-derived id with no
  `<owner>:` prefix
