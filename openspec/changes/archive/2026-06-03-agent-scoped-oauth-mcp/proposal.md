## Why

OAuth connectors and MCP servers are currently shared at the instance level: MCP
servers register globally into one `tool_registry` and connect once per `server_id`
(shared session + shared `api_key_env` credential), while the `connectors` catalog
has no owner column. Per-agent isolation today is only tool *visibility*
(`AgentSnapshot.mcp_server_ids` filters the schema). Two agents that both use
`github` share the same connection and the same credential — there is no way to give
agent A and agent B different GitHub identities or scopes. For multi-agent, multi-team
deployments this leaks capability and credentials across trust boundaries.

## What Changes

- Introduce an **agent ownership dimension** on connector and MCP server definitions:
  each connector / MCP server is bound to an owning agent, so the same logical
  `server_id` (e.g. `github`) can have a distinct configuration and credential per
  agent.
- **MCP**: move MCP server definitions from instance-global registration to
  per-agent resolution. At request time the agent loop resolves the agent's own MCP
  servers, opens (or reuses) a session keyed by `(agent, server_id)`, and registers
  tools under an agent-scoped namespace so two agents never share a connection or
  credential. **BREAKING**: MCP servers are no longer globally registered at startup
  from `config/mcp.servers.yaml` alone; global entries become a default/fallback layer.
- **OAuth**: scope connector configuration and credential resolution by owning agent.
  A connector row carries an `agent_id` (or null = global default); credential/token
  lookup is performed within the agent scope so one agent's authorization never
  satisfies another agent's tool call.
- Credentials remain **out of the database** (CLAUDE rule): per-agent secrets are
  referenced by per-scope env var names; `client_secret` is still never persisted.
- Admin surfaces (connector directory, MCP server list, authorization matrix) gain an
  agent filter and display the owning agent per entry.

## Capabilities

### New Capabilities
- `agent-scoped-connectors`: defines how OAuth connectors and MCP servers are owned by,
  configured per, and credential-resolved within an individual agent scope; covers
  scope resolution (agent-specific overrides global default), cross-agent isolation
  guarantees, and connection/session keying.

### Modified Capabilities
- `agent-resource-isolation`: the per-agent MCP allowlist requirement extends from
  visibility-only filtering to full per-agent server config + credential isolation.
- `mcp-client`: startup registration and dispatch become scope-aware; sessions are
  keyed by `(agent, server_id)` instead of `server_id` alone.
- `oauth-connector-admin`: connector directory and the authorization matrix gain an
  owning-agent dimension; credential resolution is scoped by agent.
- `mcp-server-admin`: MCP server list shows the owning agent and supports per-agent
  configuration.

## Impact

- Code: `src/fleetent/integrations/mcp/client.py` (module-global `_server_registry` /
  `_active_sessions` → scope-keyed), `src/fleetent/agent_runtime.py` (snapshot resolves
  scoped MCP servers + connector scope), `src/fleetent/agent_loop.py` (dispatch / schema
  filtering), `src/fleetent/platform/connector_management/connector_config_store.py`
  (+`agent_id` column, scoped queries), `connector_admin_api.py`, MCP server admin store/API.
- Schema: new Alembic migration adding `agent_id` (nullable, null = global default) to
  `connectors` and introducing an agent-scoped MCP server table (Alembic-owned, named
  params, no ORM).
- Config: `config/mcp.servers.yaml` becomes the global-default layer; per-agent MCP
  servers live in the DB.
- Tests: new isolation tests (agent A vs agent B same `server_id` get different
  config/credential; cross-agent call rejected); existing `agent-resource-isolation`,
  `mcp-client`, connector admin tests must not regress.
- No new dependencies; no cloud-hosted services; data stays on-prem.
