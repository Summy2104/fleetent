## MODIFIED Requirements

### Requirement: Skill list and search
The system SHALL expose `GET /admin/skills` returning all skills with name, one-line description, tags/platforms, enablement state (globally enabled / globally disabled / archived), latest security-audit verdict (pass / suspicious / rejected), cumulative injection hits, last-triggered time, and which agents enable it. Each entry SHALL also include the provenance `source` (read from the `skills` master row) and a **per-agent drift summary** (e.g. the count or list of agents whose deployed copy has `drift=1`), replacing any per-skill drift flag. The list SHALL support search and sort by name, tag, state, and audit verdict.

#### Scenario: List returns skill metadata
- **WHEN** an admin or viewer sends `GET /admin/skills`
- **THEN** the response is a JSON array where each entry contains name, description, tags, platforms, enablement state, audit verdict, injection hit count, last-triggered time, enabling agents, provenance `source`, and a per-agent drift summary
- **AND** archived skills are excluded by default

#### Scenario: Search by audit verdict
- **WHEN** `GET /admin/skills?audit=suspicious` is sent
- **THEN** only skills whose latest audit verdict is `suspicious` are returned

#### Scenario: Drift summary reflects per-agent state
- **WHEN** skill "crm-ops" is drifted on agent "support-bot" but not on others, and `GET /admin/skills` is sent
- **THEN** "crm-ops" entry's drift summary reports exactly the drifted agent(s), not a single per-skill flag
