## ADDED Requirements

### Requirement: Agent template editing

The Agents tab SHALL let an admin create, edit, and delete agent templates through a template modal capturing `id`, `display_name`, `allowed_tools`, and `system_prompt`. A "New template" control SHALL appear in the templates panel and per-template "Edit"/"Delete" actions SHALL appear in the templates list; all template write controls SHALL be hidden from viewers.

#### Scenario: Admin creates a template

- **WHEN** an admin opens the template modal, fills id/display_name/allowed_tools/system_prompt, and saves
- **THEN** the console calls `POST /admin/agent-templates` and the new template appears in the list

#### Scenario: Admin edits a template

- **WHEN** an admin opens the edit action for a template, changes a field, and saves
- **THEN** the console calls `PATCH /admin/agent-templates/{id}` and the change is reflected

#### Scenario: Admin deletes a template

- **WHEN** an admin confirms deletion of a template
- **THEN** the console calls `DELETE /admin/agent-templates/{id}` and the template disappears from the list

#### Scenario: Viewer cannot edit templates

- **WHEN** a viewer opens the Agents tab
- **THEN** the "New template" control and per-template Edit/Delete actions are hidden
