## Why

User Memory implementation has already moved into `fleetent.intelligence.memory`, and the remaining
`src/fleetent/memory_layer.py` file only re-exports the canonical public API.

Keeping the legacy import path after migration keeps tests, evaluations, and docs anchored to a flat module
that no longer owns behavior. Removing it makes the intelligence memory package the only supported
first-party boundary and prevents future changes from extending the shim.

## What Changes

- Delete `src/fleetent/memory_layer.py`.
- Migrate source, tests, and evaluation imports to `fleetent.intelligence.memory`.
- Update active spec deltas and architecture docs to describe canonical memory imports.
- Add regression coverage proving canonical memory imports remain available and `fleetent.memory_layer`
  is no longer importable.

## Out of Scope

- No memory behavior changes.
- No schema changes.
- No extraction prompt changes.
- No vector namespace changes.
- No retention or compaction policy changes.
- No memory search, vector reindex, reflection, or long-term context behavior changes.

## Module Boundary Impact

- **Owning package**：`intelligence`.
- **Public API surface**：
  - `fleetent.intelligence.memory` remains the memory public API.
  - Removed public legacy path: `fleetent.memory_layer`.
- **Owned tables**：无新增或修改；existing `memory_items` ownership remains in
  `fleetent.intelligence.memory.store`.
- **Config namespace**：无。
- **Cross-module dependencies**：
  - Long-term context, reflection, vector reindex, tests, and evaluations must import memory through
    `fleetent.intelligence.memory`.
  - Memory package must not import runtime entrypoints.
- **Migration / shim plan**：
  - Compatibility shim was created by `2026-06-02-memory-layer-package-migration`.
  - This cleanup removes the shim after first-party imports move to the canonical package.
