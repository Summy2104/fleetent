## MODIFIED Requirements

### Requirement: Agent bindings and native configuration
The agent detail view in the React SPA SHALL let an admin manage the agent and every binding **natively from one place (not deep-linked to the legacy console)**. It SHALL provide: an **edit** action that reads `GET /admin/agents/{name}` to prefill and saves via `PATCH /admin/agents/{name}`; lifecycle actions (enable, disable, archive/restore, delete with reference protection, clone); and a "manage the bound list" section for each binding type below. Each binding section SHALL read its current state from that type's **own per-type endpoint** (no aggregate `GET /admin/agents/{name}/bindings`). Every binding section SHALL show the agent's currently bound items and offer add/remove. The deploy section SHALL expose deploy/yaml export only; it SHALL NOT render version history or activation controls. All write controls SHALL be hidden from viewers.

- **Skills**: load `GET /admin/agents/{name}/skills` and toggle per skill via `PUT /admin/agents/{name}/skills/{skill_name}`.
- **Connectors**: MCP servers — options from `GET /admin/mcp/servers`, current state from `GET /admin/agents/{name}/mcp`, toggled via `POST`/`DELETE /admin/agents/{name}/mcp/{server_id}`.
- **Knowledge bases**: list via `GET /admin/agents/{name}/kbs` and bind/unbind via `POST`/`DELETE /admin/agents/{name}/kbs/{kb_id}`.
- **User access**: list via `GET /admin/agents/{name}/users` and bind/unbind via `POST`/`DELETE /admin/agents/{name}/users/{user_id}`.
- **IM access**: list the per-platform group whitelist via `GET /admin/agents/{name}/groups`, manage it via `POST /admin/agents/{name}/groups` / `DELETE /admin/agents/{name}/groups/{platform}/{group_id}`, and toggle DM / group capabilities via `PUT /admin/agents/{name}/im-capabilities`.
- **Default agent**: mark/unmark this agent as the tenant default via `PUT /admin/agents/{name}/default` / `DELETE /admin/agents/default`.
- **Secrets**: list env-var slots via `GET /admin/agents/{name}/secrets` and set/clear a value via `PUT`/`DELETE /admin/agents/{name}/secrets/{env_name}`. A secret value SHALL be write-only — never displayed in plaintext.

#### Scenario: Edit an agent from the detail view
- **WHEN** an admin opens an agent's edit action, changes a field, and saves
- **THEN** the SPA first reads `GET /admin/agents/{name}` to prefill, then calls `PATCH /admin/agents/{name}` and the change is reflected

#### Scenario: Manage bound skills / connectors / KBs / users natively
- **WHEN** an admin toggles a skill, binds/unbinds an MCP server, binds/unbinds a knowledge base, or binds/unbinds a user
- **THEN** the SPA calls the matching per-type agent binding endpoint natively (no legacy deep-link, no aggregate read) and the relevant bound list reflects the change

#### Scenario: Manage IM access
- **WHEN** an admin adds/removes an IM group from the agent's whitelist, or toggles DM / group capabilities
- **THEN** the SPA calls `POST /admin/agents/{name}/groups` (resp. `PUT /admin/agents/{name}/im-capabilities`) and the state reflects the change

#### Scenario: Set or clear the default agent
- **WHEN** an admin marks this agent as default, or clears the default
- **THEN** the SPA calls `PUT /admin/agents/{name}/default` (resp. `DELETE /admin/agents/default`)

#### Scenario: Manage secrets write-only
- **WHEN** an admin sets a secret value for an env slot, then re-opens the secrets section
- **THEN** the SPA calls `PUT /admin/agents/{name}/secrets/{env_name}`, and the value is never displayed in plaintext afterward (only the slot/status is shown)

#### Scenario: Bindings are not deep-linked to legacy
- **WHEN** an admin opens an agent's detail view
- **THEN** binding management is rendered natively in the SPA, with no "legacy entry point" deep-links for skills/connectors/KB/users

#### Scenario: Viewer cannot mutate bindings
- **WHEN** a viewer opens an agent's detail view
- **THEN** all add/remove/toggle controls across every binding section are hidden
