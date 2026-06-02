## Why

`memory_layer` can create, update, delete, search, and reindex semantic memories, but long-running
deployments still have no explicit capacity boundary. Context memories can expire for search, yet
expired rows remain in storage indefinitely. Identity and preference memories can also grow without
any maintenance signal. Over time this increases search noise, reindex cost, and reflection workload.

This change adds conservative per-user memory retention and compaction boundaries. It stays inside
semantic memory ownership and does not introduce Shared Memory, cross-user maintenance, or automatic
reflection writeback.

## What Changes

- Add a memory maintenance public API for one user at a time:
  - dry-run mode that reports expired, over-limit, and compaction candidate counts
  - apply mode that removes expired context memories from `memory_items` and vector index
  - deterministic compaction candidate detection for duplicate/near-duplicate memories
- Add configurable policy dataclasses with safe defaults:
  - per-type maximum counts
  - context expiration handling
  - duplicate compaction threshold / grouping
- Keep compaction conservative for this change:
  - it identifies candidates and can keep a canonical newest memory
  - it does not call an LLM to summarize or rewrite memories
  - it does not merge across memory types or users
- Ensure vector index cleanup mirrors removed memory rows.
- Add unit/integration tests covering dry-run, apply, user isolation, vector delete, and deterministic candidate grouping.
- Update memory docs and roadmap.

## Out of Scope

- No Shared Memory.
- No cross-user, tenant-wide, or global memory maintenance.
- No reflection-driven automatic writeback; `memory-reflection-maintenance` owns controlled reflection actions.
- No LLM summarization, rewriting, or semantic clustering.
- No scheduler/cron job, admin UI, dashboard, or alerting.
- No new persistent tables or Alembic migration.
- No change to extraction prompt or long-term context injection policy.

## Module Boundary Impact

- **Owning package**: `memory_layer` (legacy flat module, still memory-layer ownership).
- **Public API surface**: add maintenance dataclasses/functions to `fleetent.memory_layer`, including a
  per-user maintenance request/policy and summary/candidate results.
- **Owned tables**: no new tables; reads/writes existing `memory_items`.
- **Config namespace**: no production config file change in this spec; policy is passed explicitly.
- **Cross-module dependencies**: calls `vector_store.delete()` for removed memory ids through public API.
- **Migration / shim plan**: none.

## Impact

- **Runtime behavior**: no automatic maintenance is scheduled. Behavior changes only when caller explicitly
  invokes the new maintenance API.
- **Data**: apply mode may delete expired or over-limit memory rows for the specified user only. Dry-run is
  available and default tests cover it.
- **Tests**: default tests use tmp SQLite and mocked vector-store calls; no real LLM or embedding service.
