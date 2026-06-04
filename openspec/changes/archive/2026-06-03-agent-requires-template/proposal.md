# Require a template when creating an agent

## Why

Today an admin can create an agent from a blank New-agent modal. Templates exist
(`/admin/agent-templates`) but nothing ties a new agent to one, so provenance of an
agent's starting config is lost and the modal is cramped for prompt editing.

Operators want every new agent to start from a known template and want that link
**persisted** (not just a one-time prefill) so the console can later show "created
from template X".

## What Changes

- **Create requires a template.** `POST /admin/agents` gains a required `template_id`;
  requests without a valid existing template are rejected (422 missing / 404 unknown).
  Edit (PATCH) is unchanged.
- **Persisted association.** A nullable `template_id` column is added to
  `agent_versions` (Alembic 035) and threaded through `agent_store` and the console
  read seam, so the originating template id is recorded on the agent's version snapshot
  and returned by `GET /admin/agents/{name}`.
- **Wider New-agent modal.** The New-agent modal reuses the wide modal box and adds a
  required template `<select>` (populated from `GET /admin/agent-templates`) on create;
  selecting a template prefills `system_prompt`/`allowed_tools`.

## Impact

- Affected specs: `agent-versioning`, `agent-admin-api`, `agent-admin-ui`
- Affected code: `migrations/versions/035_*`, `agent_store.py`, `server.py`,
  `agent_console_api.py`, `static/admin.html`
- Backward compatibility: existing agent_versions rows keep `template_id = NULL`;
  only the create path is newly constrained.
