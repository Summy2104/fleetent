## ADDED Requirements

### Requirement: Agent create and edit

The Agents tab SHALL let an admin create a new agent and edit an existing one through a modal capturing name, system_prompt, and allowed_tools. A "New agent" control SHALL appear in the Agents bar and an "Edit" action SHALL appear in each agent row; both SHALL be hidden from viewers.

#### Scenario: Admin creates an agent

- **WHEN** an admin opens the create modal, fills name/system_prompt/allowed_tools, and saves
- **THEN** the console calls `POST /admin/agents` and the new agent appears in the list

#### Scenario: Admin edits an agent

- **WHEN** an admin opens the edit action for an agent, changes a field, and saves
- **THEN** the console first reads `GET /admin/agents/{name}` to prefill, then calls `PATCH /admin/agents/{name}`

#### Scenario: Viewer cannot create or edit

- **WHEN** a viewer opens the Agents tab
- **THEN** the "New agent" control and per-row "Edit" action are hidden

### Requirement: Agent deletion

The Agents tab SHALL let an admin hard-delete an agent from a per-row "Delete" action, after an explicit confirmation, hidden from viewers.

#### Scenario: Admin deletes an agent

- **WHEN** an admin confirms deletion of an agent
- **THEN** the console calls `DELETE /admin/agents/{name}` with the confirmation header and the agent disappears from the list

#### Scenario: Viewer cannot delete

- **WHEN** a viewer opens the Agents tab
- **THEN** the per-row "Delete" action is hidden
