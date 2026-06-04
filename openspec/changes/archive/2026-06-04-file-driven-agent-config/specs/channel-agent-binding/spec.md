## MODIFIED Requirements

### Requirement: Channel binding takes priority over user binding in agent lookup

During message routing, the channel-level agent binding SHALL be checked before the
user-level binding. At runtime this resolution SHALL be served from the file-based
agent index — a channel maps to an agent via that agent's file `bindings.channels`
entries — and SHALL return the agent's active file-sourced snapshot. No
`channel_agents` database read SHALL occur on the runtime path. The DB
`channel_agents` table (with its audit `bound_version_id`) remains the authoring
record from which agent files are generated.

#### Scenario: Message in channel with binding

- **WHEN** a message arrives in a channel listed in some agent's file `bindings.channels`
- **THEN** that agent is used, regardless of whether the user has their own binding, and
  no `channel_agents` table read occurs

#### Scenario: Message in channel without binding, user has binding

- **WHEN** a message arrives in a channel that no agent file binds, but the user is
  listed in some agent's file `bindings.users`
- **THEN** the user's agent is used

#### Scenario: Channel not bound by any agent file

- **WHEN** no agent file lists the incoming `(platform, channel_id)`
- **THEN** channel resolution yields nothing and routing falls through to the user
  binding, then the default agent
