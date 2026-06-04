## Context

`normalizer.route` today gates messages via `im_channel_allowlist.is_allowed(owner,…)`
and `im_user_store.check_allowed_by_user_id` — both owner-keyed, platform-DB-backed.
The agent definition is already file-driven (`agent_config`, single-file agent home).
To make an agent a self-contained process, its IM access must also be local to the agent
home with no platform-DB dependency at runtime.

## Goals / Non-Goals

**Goals**
- Per-agent IM access: static allow rules (channels/users) + dynamic approvals, scoped to
  one agent.
- Agent-home-local: static rules materialized into the agent home; approvals in an
  agent-local store under the home `data/`.
- Runtime gates evaluate locally with zero platform-DB read.

**Non-Goals**
- The platform authoring UI/CLI for editing per-agent allowlists (lands with the
  platform changes); this change provides the runtime + home format + materialization
  contract.
- Removing the owner-level tables (kept for platform authoring history).

## Decisions

### D1: Access lives in the agent home
`agent.yaml` gains an `access` block: `allow_channels: [...]`, `allow_users: [...]`,
`require_approval: bool`. Static, platform-authored, materialized with the rest of the
home config.

### D2: Approvals in an agent-local store
A per-agent approval store under the agent home `data/` (e.g. `data/im_approvals.json`
or a local SQLite) records pending→approved IM users at runtime. The agent runtime owns
it; no platform DB. (Resolves the "dynamic approval write-back" open item: it writes
local.)

### D3: route() evaluates locally
`route` resolves the agent (already file-sourced), then checks: channel ∈
`access.allow_channels` (empty = allow all the agent's bound channels), and user
allowed = user ∈ `allow_users` OR approved in the local store; if `require_approval` and
not approved, reply with the rejection/approval prompt. No `im_channel_allowlist` /
`im_user_store` read on this path.

### D4: Platform side keeps authoring
Platform editing of per-agent allowlists writes the materialized `access` block / home
file (the materialization mechanics land in `platform-agent-lifecycle`). The owner-level
tables stay for the platform's own records but are off the runtime path.

## Risks / Trade-offs

- **Two stores during transition** (owner DB vs per-agent local) → runtime reads only the
  local; platform authoring still writes DB + materialization. Documented.
- **Approval durability**: agent-local approval store lives in the agent home `data/`;
  backed up with the home. Acceptable for a self-contained agent.
- **BREAKING runtime gate source** → mitigate by landing before/with `agent-runtime-cli`
  and migrating affected tests.

## Migration Plan

1. Add `access` block to the agent home model + an agent-local approval store.
2. Rewire `route` to local gates (replace owner-DB lookups).
3. Migrate affected allowlist/route tests to the per-agent local model.
4. Platform authoring/materialization wiring is deferred to `platform-agent-lifecycle`.

## Open Questions

- Approval-store format (json vs local SQLite) — decide at apply time; json is simplest
  for a single self-contained agent.
