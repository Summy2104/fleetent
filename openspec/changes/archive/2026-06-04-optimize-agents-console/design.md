## Context

Agents is the last admin module on the legacy table + multi-modal flow. Skills and Connectors already use a card-grid + right-hand detail drawer, and the sidebar was just modernized. The backend already has stores + endpoints for most bindings (users, channels, skills, MCP servers) but two gaps exist: knowledge-base bindings have a store (`agent_kbs`) and only KB-side endpoints, and OAuth connectors have no per-agent binding at all. The create/edit modal can create but the edit path is unwired. Runtime resolution is file-driven (`agent_config`/`agent.yaml`, PR #101); this change is authoring/admin-only and must not touch runtime resolution.

## Goals / Non-Goals

**Goals:**
- One agent detail drawer that does CRUD + manages every binding (skills, MCP + OAuth connectors, knowledge bases, IM channels/users) with a "show bound list + add/remove" pattern.
- Reuse existing endpoints/stores; add only the missing agent-side surface (KB endpoints, OAuth binding store + endpoints).
- Visual + interaction parity with Skills/Connectors (card grid, toolbar, drawer, pills, viewer gating).

**Non-Goals:**
- No change to runtime agent resolution or `agent_config` file generation.
- No new agent template features beyond what exists.
- No bulk operations or agent-level observability redesign (existing seam stays).
- Not reconciling the file-vs-DB authoring pipeline (out of scope).

## Decisions

- **Card grid + drawer over table + modals.** Mirror Skills: `loadAgents()` → `agentCardHtml()` into a grid; clicking a card opens a drawer (`#ag-drawer`, reuse `.conn-drawer` classes) holding metadata, lifecycle actions, Versions, and one section per binding type. Rationale: consistency + the drawer is the natural home for per-agent binding management; the old `#ag-bind-modal`/`#ag-modal` are removed. Edit stays a small modal launched from the drawer (prefill via `GET /admin/agents/{name}`, save via `PATCH`).
- **Binding sections = manage-the-list.** Each section shows currently-bound items as removable rows plus an "add" control (select of available items). Skills/MCP reuse existing toggle endpoints; KB and OAuth use the new endpoints. Rationale: matches the requirement ("manage bound X list") and the Connectors drawer tool-list feel.
- **KB binding: agent-side endpoints over the existing store.** Add `GET/POST/DELETE /admin/agents/{name}/kbs` in `agent_admin_api`, delegating to `agent_kbs_store` (resolve name→id, use agent tenant). No new table. Rationale: the store + KB-side endpoints already exist; only the agent-facing surface is missing.
- **OAuth binding: new parallel store + table.** Add `agent_oauth_bindings(agent_id, connector_id, created_at, created_by)` via Alembic, a store mirroring `agent_store.bind_mcp_server`, and `GET/POST/DELETE /admin/agents/{name}/bindings/oauth/{connector_id}` validating the connector exists in `connector_config_store`. Rationale: OAuth connectors have no per-agent concept today; a thin allowlist binding parallels MCP and is the least-surprising model. Alternative considered: reuse the agent-scoped connector *config* rows (migration 040) — rejected, those are per-agent credential overrides, not an allowlist, and overloading them would conflate two concepts.
- **No runtime wiring.** Bindings remain authoring metadata; whether/how the agent loop consumes OAuth bindings is a separate follow-up, consistent with how KB/MCP bindings are authored today.

## Risks / Trade-offs

- [New migration on a heavily-migrated chain] → keep it a single additive `CREATE TABLE` at head; round-trip tested (upgrade/downgrade) like 043/044.
- [admin.html is large and shared; UI tests grep markup] → update `test_admin_console_ui.py` agent assertions to the new card/drawer markers; keep `data-tab="agents"` and function-name hooks the tests rely on, or update them in lockstep.
- [OAuth binding without runtime consumption may look inert] → document it as authoring-only (same status as today's bindings); the management UX is still the deliverable.
- [Removing `#ag-bind-modal`/old flow could break other references] → grep for `agOpenBind`/`ag-bind-*`/`ag-modal` and remove/redirect all call sites in one pass.

## Migration Plan

- Additive Alembic migration for `agent_oauth_bindings`; no data backfill. Rollback = downgrade drops the table (no dependents).
- Frontend is a static asset swap (no migration); ship behind the existing Agents tab.

## Open Questions

- Should OAuth connector bindings later gate which connectors the agent loop exposes? Deferred — out of scope here; this change only authors the binding.
