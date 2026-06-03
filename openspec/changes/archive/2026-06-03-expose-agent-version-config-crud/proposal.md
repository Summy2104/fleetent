## Why

Agent runtime (`agent_runtime.AgentSnapshot` + `agent_loop`) already consumes four per-version fields — `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace` — and `agent_store.create_agent`/`create_version` already persist them. But the admin Agent CRUD (create/edit endpoints and the admin.html modal) only exposes `system_prompt` and `allowed_tools`. So an admin cannot configure skills, MCP allowlist, model overrides, or memory namespace from the console; these can only be set via CLI/apply specs. This closes that gap so the console CRUD is complete with respect to what the runtime actually uses.

## What Changes

- `POST /admin/agents` (CreateBody) accepts optional `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`, passing them through to `agent_store.create_agent`.
- `PATCH /admin/agents/{name}` (UpdateBody) accepts the same four fields as optional partial overrides, creating a new version with only the provided fields changed (immutable-snapshot edit).
- `GET /admin/agents/{name}` returns the four fields from the active version so the edit modal can prefill.
- The create/edit seams (`create_agent_def`, `update_agent_def`) and their server.py wiring carry the four fields through to the store.
- admin.html create/edit modal gains inputs for the four fields (admin-gated, same as existing controls).
- hermes-inspired fields that the runtime does NOT yet consume (`max_turns`, `reasoning_effort`, memory toggles/limits, `session_reset`, `delegation` limits, `code_execution` limits, `personalities`) are documented in design.md as future work requiring a migration + agent_loop wiring — explicitly OUT of scope here.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `agent-admin-api`: the create/read-full/update endpoints extend their accepted/returned fields to include `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`.
- `agent-admin-ui`: the create/edit modal captures the four additional version-config fields.

## Impact

- Code: `agent_console_api.py` (CreateBody/UpdateBody/_def_response/create+patch+get routes, seams), `server.py` (seam wiring wrappers), `static/admin.html` (modal inputs + JS).
- No DB migration: `agent_versions` already has all four columns and `agent_store` already reads/writes them.
- No runtime change: `agent_loop`/`agent_runtime` already consume the fields.
- Auth/role gating, confirmation semantics unchanged.
