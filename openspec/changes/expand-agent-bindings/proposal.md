## Why

The Agent **Bindings** modal today only binds users and channels through two raw
text-input rows. Mature agent platforms (Claude, OpenAI Assistants, Dify) let an
operator attach an agent's *resources* — which skills it may use, which MCP/tool
servers it connects to — and configure its IM deployment, all from one place.

fleetent already has most of the plumbing but it is scattered and partly inert:

- `agent_skills` (skill↔agent matrix) exists and is editable **only from the Skills
  page**, and is **not consumed at runtime** — disabling a skill for an agent has no
  effect on what gets injected.
- MCP servers can only be attached through the immutable `mcp_server_ids`
  version-config field, which was deliberately removed from the agent modal; there is
  no per-agent MCP binding.
- Channel bindings are created blind (no list of an agent's current channels, no way
  to see/repair the version pin) and there is no read endpoint to review them.

This change consolidates skill, MCP, and IM/channel binding management into the agent
Bindings surface and makes skill/MCP bindings actually affect agent execution.

## What Changes

- **Skill bindings (agent side + runtime):** the Bindings modal lists every skill with
  a per-agent enable toggle, backed by the existing `agent_skills` table. A new
  agent-centric read route returns skills with this agent's enable state. The agent
  runtime restricts skill injection to the agent's enabled skills when any binding
  exists (fallback: all skills, preserving today's behavior for unbound agents).
- **MCP bindings (new):** a new `agent_mcp_servers(agent_id, server_id)` binding table,
  agent-centric routes to list/bind/unbind, and a multi-select in the Bindings modal
  populated from `GET /admin/mcp/servers`. The runtime unions an agent's bound MCP
  server ids into the set used to filter tool schemas.
- **IM/channel binding config:** a read endpoint returns an agent's current user and
  channel bindings (with `bound_version_id`); the Bindings modal renders the channel
  list with platform/channel/version and an unbind control, on top of the existing
  bind-by-input row.

## Capabilities

### New Capabilities
- `agent-mcp-binding`: per-agent MCP server binding storage, admin routes, and runtime
  tool-schema resolution.

### Modified Capabilities
- `skill-agent-binding`: agent-side editing route and runtime injection now honor the
  `agent_skills` enable state.
- `agent-admin-api`: agent-centric binding read routes and MCP bind/unbind routes.
- `agent-admin-ui`: Bindings modal gains Skills, MCP, and channel-list sections.
- `agent-invocation`: skill index and MCP tool filtering resolve per-agent bindings.

## Impact

- Migration: new `agent_mcp_servers` table (Alembic, next revision after 035).
- Stores: new `agent_mcp_store` (or functions in `agent_store`); reuse
  `skill_admin_store` for skills.
- API: `src/fleetent/platform/agent_management_console/agent_admin_api.py` (new routes);
  `agent_console_api.py` if needed for reads.
- Runtime: `src/fleetent/agent_loop.py` skill index + `filter_tool_schemas`;
  `src/fleetent/skill_registry.py` `SkillIndex` gains an optional allowlist.
- UI: `src/fleetent/static/admin.html` Bindings modal.
- Tests: integration (migration, store, api, ui-string), unit (runtime resolution).
