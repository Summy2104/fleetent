## MODIFIED Requirements

### Requirement: Agent template editing

The admin console SHALL keep a single **Agents** sidebar item and surface **Agents** and **Templates** as two sub-tabs inside the Agents page header. Selecting the Templates sub-tab SHALL let an admin create, edit, and delete agent templates through a template modal capturing `id`, `display_name`, `allowed_tools`, and `system_prompt`. A "New template" control SHALL appear in the Templates sub-tab and per-template "Edit"/"Delete" actions SHALL appear in the templates list; all template write controls SHALL be hidden from viewers. There SHALL be no separate Templates sidebar nav item.

#### Scenario: Templates is an Agents-page sub-tab

- **WHEN** the admin opens the Agents tab
- **THEN** the page header shows `Agents` and `Templates` sub-tabs, there is no separate Templates sidebar nav item, and selecting the Templates sub-tab shows the templates list

#### Scenario: Admin creates a template

- **WHEN** an admin opens the Templates sub-tab, opens the template modal, fills id/display_name/allowed_tools/system_prompt, and saves
- **THEN** the console calls `POST /admin/agent-templates` and the new template appears in the list

#### Scenario: Admin edits a template

- **WHEN** an admin opens the edit action for a template, changes a field, and saves
- **THEN** the console calls `PATCH /admin/agent-templates/{id}` and the change is reflected

#### Scenario: Admin deletes a template

- **WHEN** an admin confirms deletion of a template
- **THEN** the console calls `DELETE /admin/agent-templates/{id}` and the template disappears from the list

#### Scenario: Viewer cannot edit templates

- **WHEN** a viewer opens the Templates sub-tab
- **THEN** the "New template" control and per-template Edit/Delete actions are hidden
