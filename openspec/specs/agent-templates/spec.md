# agent-templates Specification

## Purpose
Store-backed, editable agent templates (creation presets: display_name + allowed_tools + system_prompt) seeded from the original built-ins.
## Requirements

### Requirement: Agent template storage

The system SHALL store agent templates in an `agent_templates` SQLite table with columns: `id` (TEXT PRIMARY KEY), `display_name` (TEXT), `allowed_tools` (TEXT, JSON array), `system_prompt` (TEXT), `created_at`, `updated_at`. Schema lifecycle SHALL be owned by an Alembic migration that creates the table and seeds the three built-in templates (`readonly-qa`, `ops`, `support`) from their current definitions. SQL SHALL use named parameters and go through the store boundary; no ORM.

#### Scenario: Migration creates table and seeds built-ins

- **WHEN** the Alembic migration runs against an existing database
- **THEN** an `agent_templates` table exists and contains rows for `readonly-qa`, `ops`, and `support` with their built-in `display_name`/`allowed_tools`/`system_prompt`

### Requirement: Agent template store CRUD

The `agent_template_store` SHALL expose `list_templates()`, `get_template(id)`, `create_template(id, display_name, allowed_tools, system_prompt)`, `update_template(id, *, display_name?, allowed_tools?, system_prompt?)`, and `delete_template(id)`.

#### Scenario: List returns seeded templates

- **WHEN** `agent_template_store.list_templates()` is called on a freshly migrated database
- **THEN** it returns the three seeded templates, each with `id`, `display_name`, `allowed_tools`, and `system_prompt`

#### Scenario: Create persists a new template

- **WHEN** `agent_template_store.create_template("triage", "Triage", ["read_*"], "You triage.")` is called
- **THEN** `get_template("triage")` returns that template

#### Scenario: Create duplicate id rejected

- **WHEN** `create_template` is called with an `id` that already exists
- **THEN** it raises and no second row is written

#### Scenario: Update overrides only provided fields

- **WHEN** `update_template("ops", system_prompt="v2")` is called
- **THEN** `get_template("ops").system_prompt == "v2"` and its `allowed_tools` is unchanged

#### Scenario: Update missing template

- **WHEN** `update_template` targets an `id` that does not exist
- **THEN** it returns a falsey result and writes nothing

#### Scenario: Delete removes a template

- **WHEN** `delete_template("support")` is called
- **THEN** `get_template("support")` is `None` and the call returns `True`

#### Scenario: Delete missing template returns False

- **WHEN** `delete_template("nope")` is called and no such template exists
- **THEN** no rows change and the call returns `False`
