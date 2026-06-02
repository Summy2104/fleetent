# skill-agent-binding Specification

## Purpose
TBD - created by archiving change 2026-06-02-skill-management. Update Purpose after archive.
## Requirements
### Requirement: Skill-to-Agent matrix
The system SHALL maintain a Skill ↔ Agent binding (`agent_skills`) expressing which skills are available to which agent. The binding SHALL be editable both from an agent's detail (selecting available skills) and from a skill's detail (viewing/adjusting the agents that enable it), backed by the same reference view.

#### Scenario: List agents enabling a skill
- **WHEN** an admin sends `GET /admin/skills/{name}/agents`
- **THEN** the response lists every agent and whether it has the skill enabled

#### Scenario: Edit binding from agent side
- **WHEN** an admin enables skill "crm-ops" for agent "support-bot"
- **THEN** an `agent_skills` row with `enabled=1` is recorded for `(support-bot, crm-ops)` and the action is audited

### Requirement: Per-agent enable/disable
The system SHALL allow disabling a skill at the agent level (`agent_skills.enabled=0`) independent of its global state. A skill disabled for one agent SHALL NOT be injected for that agent while other agents that enable it continue to inject it normally.

#### Scenario: Per-agent disable is scoped
- **WHEN** skill "crm-ops" is globally enabled but disabled for agent "support-bot", and a request that would trigger it arrives via "support-bot"
- **THEN** "support-bot" does not inject "crm-ops" while other agents that enable it still inject it normally
- **AND** the disable action is audited

### Requirement: Reference view reused for deletion protection
The same `agent_skills` reference view SHALL be the source for archival reference protection — querying which agents still have a skill enabled (`enabled=1`).

#### Scenario: Reference view reports occupying agents
- **WHEN** archival of a skill is attempted
- **THEN** the reference view returns the agents with `enabled=1`, which the archive endpoint uses to block deletion when non-empty

