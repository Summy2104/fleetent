## MODIFIED Requirements

### Requirement: Agent lifecycle and clone

The console SHALL let an admin enable, disable, archive, restore, and clone an agent, and view observability, calling the matching endpoints. The per-row agent actions SHALL be collapsed into a single `⋯` overflow menu rather than rendered as a flat button row; admin-only items SHALL remain hidden for viewers. The overflow menu SHALL also offer a **Deploy** action that binds the agent to an IM channel (`platform` + `channel_id`) via the existing channel-binding endpoint, putting the agent live on that channel.

#### Scenario: Clone an agent

- **WHEN** an admin clones an agent
- **THEN** the console calls `POST /admin/agents/{name}/clone` and the new agent appears

#### Scenario: Row actions live in an overflow menu

- **WHEN** an admin views the agents list
- **THEN** each row's actions are reached through a `⋯` overflow menu (not a flat row of buttons)
- **AND** the menu contains the existing actions (stats, versions, edit, bindings, clone, enable/disable, archive/restore, delete)
- **AND** viewer sessions still hide the admin-only items

#### Scenario: Deploy an agent to a channel

- **WHEN** an admin chooses Deploy from the overflow menu and supplies a platform and channel_id
- **THEN** the console calls `POST /admin/agents/{name}/bindings/channels/{platform}/{channel}` to put the agent live on that channel
