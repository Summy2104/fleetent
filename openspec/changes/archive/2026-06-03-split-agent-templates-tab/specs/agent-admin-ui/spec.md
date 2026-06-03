## MODIFIED Requirements

### Requirement: Agent template editing

The admin console SHALL provide a dedicated **Templates** tab (under the Agents group) that lets an admin create, edit, and delete agent templates through a template modal capturing `id`, `display_name`, `allowed_tools`, and `system_prompt`. A "New template" control SHALL appear in the Templates tab and per-template "Edit"/"Delete" actions SHALL appear in the templates list; all template write controls SHALL be hidden from viewers. The Agents tab SHALL no longer contain template controls.

#### Scenario: Templates tab is a sibling of Agents

- **WHEN** the admin console renders the sidebar navigation
- **THEN** a `Templates` nav item (its own `#tab-templates` section) appears under the Agents group, separate from the Agents tab, and the Agents tab no longer shows a "Templates" toggle

#### Scenario: Admin creates a template

- **WHEN** an admin opens the Templates tab, opens the template modal, fills id/display_name/allowed_tools/system_prompt, and saves
- **THEN** the console calls `POST /admin/agent-templates` and the new template appears in the list

#### Scenario: Admin edits a template

- **WHEN** an admin opens the edit action for a template, changes a field, and saves
- **THEN** the console calls `PATCH /admin/agent-templates/{id}` and the change is reflected

#### Scenario: Admin deletes a template

- **WHEN** an admin confirms deletion of a template
- **THEN** the console calls `DELETE /admin/agent-templates/{id}` and the template disappears from the list

#### Scenario: Viewer cannot edit templates

- **WHEN** a viewer opens the Templates tab
- **THEN** the "New template" control and per-template Edit/Delete actions are hidden
