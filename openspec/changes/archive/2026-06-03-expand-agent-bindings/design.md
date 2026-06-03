## Context

The agent execution snapshot (`agent_versions`) carries `skills_dir` and
`mcp_server_ids` as immutable version config. A prior change removed those raw fields
from the agent modal so only template-backed fields (`system_prompt`, `allowed_tools`)
are edited there. Separately, `agent_skills` is a live (non-snapshot) matrix editable
from the Skills page but inert at runtime. This change introduces *bindings* — live,
per-agent resource attachments resolved at session start — without reintroducing raw
config inputs to the modal.

## Goals / Non-Goals

**Goals**
- Skill, MCP, and channel binding management reachable from the agent Bindings modal.
- Skill and MCP bindings actually affect agent execution.
- Reuse existing tables/stores where they already exist (`agent_skills`,
  `channel_agents`, `user_agents`).

**Non-Goals**
- No change to the agent create/edit modal field set (still template-backed only).
- No removal of the `skills_dir` / `mcp_server_ids` version-config fields; bindings layer
  *on top of* the snapshot, they do not replace it.
- No per-binding IM credential/secret management (connectors own secrets).

## Key Decision: bindings layer over the snapshot, not into it

Two models were considered for skills/MCP:

- **(A) Version-config**: editing skills/MCP creates a new version snapshot.
- **(B) Binding tables**: live join rows resolved at runtime, no new version.

**Chosen: (B).** The user framed this as "bindings"; mature agents expose
toggleable per-agent resources; `agent_skills` already follows this model. Editing a
binding must NOT mint a new version (that would conflate resource attachment with the
prompt/tools snapshot lifecycle).

**Runtime resolution (union/intersect semantics):**

- *Skills*: if the agent has **any** `agent_skills` rows, the effective skill set is the
  enabled (`enabled=1`) subset; if it has **no** rows at all, fall back to every skill in
  `skills_dir` (today's behavior — no silent breakage for unbound agents).
- *MCP*: the effective MCP server set is the **union** of `mcp_server_ids` from the
  snapshot and the agent's `agent_mcp_servers` bindings. Bindings can only *add* servers,
  never remove snapshot ones.

This keeps unbound/legacy agents behaving exactly as before while making bindings
additive and predictable.

## Data model

New table (Alembic revision after 035):

```
agent_mcp_servers(
  agent_id   INTEGER NOT NULL REFERENCES agents(id),
  server_id  TEXT    NOT NULL,
  created_at TEXT    NOT NULL,
  created_by TEXT,
  PRIMARY KEY (agent_id, server_id)
)
```

Reused as-is: `agent_skills(agent_id, skill_name, enabled, ...)`,
`channel_agents(platform, channel_id, agent_id, bound_version_id, ...)`,
`user_agents(user_id, agent_id)`.

`server_id` is a free TEXT value validated against `GET /admin/mcp/servers` at the API
layer (not an FK — MCP servers are config, not a DB table here), mirroring how
`template_id` existence is checked on agent create.

## API surface (`/admin` prefix)

Read:
- `GET /admin/agents/{name}/bindings` → `{users:[...], channels:[{platform,channel_id,bound_version_id}], mcp_servers:[server_id]}`
- `GET /admin/agents/{name}/skills` → `[{skill_name, enabled}]` (every known skill with this agent's state)

Write (admin-only, audited):
- `PUT /admin/agents/{name}/skills/{skill_name}` body `{enabled: bool}` → upsert `agent_skills`
- `POST /admin/agents/{name}/bindings/mcp/{server_id}` → insert binding (404 if server unknown)
- `DELETE /admin/agents/{name}/bindings/mcp/{server_id}` → delete binding

Existing user/channel bind/unbind routes are unchanged.

## Runtime wiring

- `skill_registry.SkillIndex.__init__` gains `allowed: set[str] | None = None`; when set,
  `match()`/index only considers skills whose name is in `allowed`.
- `agent_loop` (both `run` and `run_stream` paths): before building the SkillIndex,
  resolve the agent's `agent_skills`; if non-empty, pass the enabled names as `allowed`.
- `agent_loop`: compute `eff_mcp = (snapshot.mcp_server_ids or []) ∪ agent_mcp_servers`
  and pass to `filter_tool_schemas`.
- Resolution needs the agent id/name in the loop. The loop already has the version
  snapshot; thread the agent name (or id) so the store lookups can run. Lookups are
  cheap single-row queries done once per session start, consistent with existing
  `get_async_client_and_config`-style per-invocation work.

## UI (admin.html Bindings modal)

The modal keeps the existing user-bind and channel-bind input rows and adds:

- **Skills** section: on open, `GET /admin/agents/{name}/skills`; render a checkbox list;
  toggling a box calls the `PUT .../skills/{skill_name}`.
- **MCP** section: `GET /admin/mcp/servers` for options + `GET .../bindings` for current;
  render checkboxes; toggle calls POST/DELETE `.../bindings/mcp/{server_id}`.
- **Channels** section: render the channel list from `GET .../bindings` with an unbind
  button per row (calls existing DELETE channel route).

All write controls remain gated behind `IS_VIEWER`.

## Risks / Mitigations

- *Runtime regression for unbound agents*: mitigated by the "no rows → all skills"
  fallback and MCP union semantics (additive only).
- *Skill name vs file identity*: skills are keyed by `name` from `skill_registry`;
  `agent_skills.skill_name` already uses that key — consistent.
- *Scope size*: change spans migration→runtime→UI; tasks are ordered so each layer is
  independently TDD-verifiable, and skill/MCP/IM are separable task groups.

## Migration / Rollout

Additive migration; downgrade drops `agent_mcp_servers`. No data backfill. Existing
agents gain empty binding sets and behave unchanged until an admin binds resources.
