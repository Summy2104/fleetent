# 2026-06-13: Retire Cross-Run Layered Budget

## Context

AR18 introduced an opt-in cross-run budget that accumulated turns and tokens across
session, user, and agent scopes. In practice it stayed dormant by default, no active
deployment depended on it, and it carried semantic gaps around retention windows and
operational clarity.

## Decision

- Remove the capability completely rather than leaving dormant config or wiring.
- Keep AR2 per-run iteration/token budgeting unchanged, including the Grace Call path.
- Retire the agent-state persistence for this feature with a forward-only head migration
  that drops the historical table on open.
- Continue tolerating legacy YAML keys during file load so older generated configs still
  boot while the schema no longer exposes those fields.

## Consequences

- Runtime and boot wiring get simpler: one budget system remains, and it is scoped to a
  single run.
- The historical table is intentionally discarded at head; rebuilds should come from git
  history rather than from partial stubs left in the live codebase.
- Documentation now describes the per-agent state schema without the retired table.
