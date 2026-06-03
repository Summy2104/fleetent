## MODIFIED Requirements

### Requirement: Agents management tab

The admin console SHALL present an Agents tab listing each agent with its status, and
SHALL list available agent templates. Write controls SHALL be admin-only. The New-agent
modal SHALL use the wide modal box and, in create mode only, SHALL present a required
template `<select>` populated from `GET /admin/agent-templates`; selecting a template
SHALL prefill the system prompt and allowed tools, and the create request SHALL include
the chosen `template_id`. Saving a new agent without a selected template SHALL be
blocked client-side. The agent modal SHALL expose only the template-backed editable
fields — `system_prompt` and `allowed_tools` (plus the agent `name` and template on
create) — and SHALL NOT present `skills_dir`, `mcp_server_ids`, `model_overrides`, or
`memory_namespace` inputs; create and edit requests SHALL omit those fields so they fall
back to defaults or inherit the prior version.

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

#### Scenario: Modal exposes only template-backed fields

- **WHEN** an admin opens the New-agent or Edit-agent modal
- **THEN** only the `name`/template, `system_prompt`, and `allowed_tools` controls are present
- **AND** no `skills_dir`, `mcp_server_ids`, `model_overrides`, or `memory_namespace` input is shown
- **AND** saving sends only `system_prompt` and `allowed_tools` (plus `name`/`template_id` on create)
