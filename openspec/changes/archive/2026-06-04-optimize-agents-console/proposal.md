## Why

The Agents console is the only major module still on the old table-plus-modal pattern, while Skills and Connectors were redesigned to a card-grid + detail-drawer layout. It is also incomplete: the create/edit modal can create but not edit an agent, and the bindings modal only manages users, channels, skills and MCP servers — there is no way to bind or manage **knowledge bases** or **OAuth connectors** from the agent side, even though the stores exist. Operators need one clean place per agent to do CRUD and manage every binding.

## What Changes

- Redesign the Agents tab to the established card-grid + detail-drawer style (consistent with Skills/Connectors and the new sidebar): searchable/filterable agent cards, a detail drawer with metadata and per-binding management sections.
- Agent CRUD from the drawer: create, **edit** (system prompt / allowed tools / model overrides — currently not wired), enable, disable, archive/restore, delete (with reference protection), clone, and version activation.
- Per-agent binding management, each as a "manage the bound list" section in the drawer:
  - **Skills** — bind/unbind, see the bound-skills list (reuse `agent-skill-scoping`).
  - **Connectors** — MCP servers (reuse `agent-mcp-binding`) **and** OAuth connectors (new per-agent binding).
  - **Knowledge bases** — bind/unbind from the agent, see the bound-KB list (agent-side surface over the existing `agent_kbs` store).
  - **IM** — channel and user bindings (reuse `channel-agent-binding` + user bindings).
- Add the missing backend surface: agent-side knowledge-base binding endpoints and per-agent OAuth-connector binding (store + endpoints), so the UI can manage them from the agent.
- Authoring stays DB-sourced; runtime stays file-driven (`agent_config` / `agent.yaml`). This change only touches the DB authoring + admin surface, not runtime resolution.

## Capabilities

### New Capabilities
- `agent-oauth-binding`: per-agent OAuth-connector binding — a store + admin endpoints to bind/unbind/list which OAuth connectors an agent may use (parallels `agent-mcp-binding` for MCP servers).

### Modified Capabilities
- `agent-admin-ui`: replace the table + bindings-modal layout with a card grid + detail drawer; add agent editing and the per-binding "manage list" sections for skills, connectors (MCP + OAuth), knowledge bases and IM.
- `agent-admin-api`: add agent-side endpoints to list/bind/unbind knowledge bases for an agent (over the existing `agent_kbs` store), and to list/bind/unbind OAuth connectors, completing the per-agent binding surface.

## Impact

- Backend: `src/fleetent/platform/agent_management_console/agent_admin_api.py` (new KB + OAuth binding endpoints), a new per-agent OAuth binding store + Alembic migration, reuse of `agent_kbs_store`, `agent_store`, `skill_admin_store`.
- Frontend: `src/fleetent/static/admin.html` — Agents tab markup, CSS, and JS (card grid + drawer + binding sections), replacing the current `#ag-modal`/`#ag-bind-modal` flow.
- Tests: `tests/integration/test_agent_admin_api.py`, `test_agent_console_api.py`, `test_admin_console_ui.py`, new store test, migration test.
- No runtime/agent-loop changes; no change to `agent_config` file resolution.
