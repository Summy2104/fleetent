## ADDED Requirements

### Requirement: Managed / adhoc provenance badge
Each agent SHALL carry a `provenance` flag valued `managed` or `adhoc`. Agents created, cloned, or created-from-template through the management console SHALL default to `adhoc`. Agents compiled by askit `deploy --target fleetent` SHALL be `managed`. The management view SHALL render a badge reflecting `provenance`.

#### Scenario: Console-created agent is adhoc
- **WHEN** an admin creates, clones, or creates-from-template an agent in the console
- **THEN** the new agent's `provenance` is `adhoc`

#### Scenario: Deployed agent is managed
- **WHEN** askit `deploy --target fleetent` writes an agent from a spec
- **THEN** that agent's `provenance` is `managed` and the console shows a managed badge

### Requirement: Stable identity across provenance changes
The agent identity SHALL be the stable `agent_id`. Switching `provenance` between `managed` and `adhoc` SHALL be a flag flip on the same row and SHALL NOT recreate the agent, change its id, or lose its versions and bindings.

#### Scenario: Provenance flip preserves identity
- **WHEN** an agent's `provenance` is changed from `adhoc` to `managed` (or back)
- **THEN** the agent keeps the same `agent_id`, `active_version_id`, version history, and all bindings

### Requirement: Drift flag on managed agents
A UI modification (edit, toggle, model change) to a `managed` agent SHALL set its `drift` flag and SHALL be reflected as a drift badge. The flag SHALL be the only state this change maintains; reconciliation (accepting drift into spec, or overlay reflow reverting it) is owned by askit.

#### Scenario: UI change on managed agent marks drift
- **WHEN** an admin edits a `managed` agent in the console
- **THEN** the agent's `drift` flag is set and the console shows a drift badge

#### Scenario: UI change on adhoc agent does not mark drift
- **WHEN** an admin edits an `adhoc` agent
- **THEN** no `drift` flag is set (drift is meaningful only for managed agents)

#### Scenario: Reconciliation is delegated to askit
- **WHEN** drift needs to be promoted to spec or reverted
- **THEN** this change only exposes the `provenance`/`drift` flags and defers the reflow to askit `deploy --target fleetent`
