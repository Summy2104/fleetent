## MODIFIED Requirements

### Requirement: Agents management tab

The admin console SHALL present an Agents tab listing each agent with its status, and
SHALL list available agent templates. Write controls SHALL be admin-only. The New-agent
modal SHALL use the wide modal box and, in create mode only, SHALL present a required
template `<select>` populated from `GET /admin/agent-templates`; selecting a template
SHALL prefill the system prompt and allowed tools, and the create request SHALL include
the chosen `template_id`. Saving a new agent without a selected template SHALL be
blocked client-side.

#### Scenario: Admin sees agents and templates

- **WHEN** an admin opens the Agents tab
- **THEN** agents are listed via `GET /admin/agents` and templates via `GET /admin/agent-templates`

#### Scenario: Viewer cannot mutate agents

- **WHEN** a viewer opens the Agents tab
- **THEN** enable / disable / archive / restore / clone / bind controls are hidden

#### Scenario: New-agent modal requires a template

- **WHEN** an admin opens the New-agent modal
- **THEN** the modal uses the wide box and shows a required template `<select>` populated from the templates endpoint
- **AND** attempting to save without choosing a template is blocked
- **AND** choosing a template prefills the system prompt and allowed tools and sends `template_id` on create
