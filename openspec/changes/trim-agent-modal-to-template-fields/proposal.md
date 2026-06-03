# Trim the agent modal to template-backed fields

## Why

The New/Edit-agent modal exposes skills_dir, mcp_server_ids, model_overrides, and
memory_namespace. Templates only carry `system_prompt` and `allowed_tools`, and agents
are now created from a template, so those extra free-form fields confuse operators and
have no template source. The modal should only let an operator edit what a template
provides.

## What Changes

- Remove the `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`
  inputs from the agent modal.
- `agCreate`/`agEdit`/`agSave` no longer read or send those fields; create/edit send
  only `system_prompt` and `allowed_tools` (plus `name`/`template_id` on create).
- Backend create/update seams keep accepting the omitted fields (they simply
  default/inherit), so no API or schema change is needed.

## Impact

- Affected specs: `agent-admin-ui`
- Affected code: `static/admin.html`
- Backward compatibility: omitted fields fall back to existing defaults on create and
  inherit the prior version on edit; existing agents are unaffected.
