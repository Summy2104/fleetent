## Context

The current memory model already distinguishes long-lived `identity` / `preferences` memories from
TTL-based `context` memories. Search filters expired context rows, and `iter_indexable_memories()`
excludes expired context rows for reindex. That avoids injecting expired context, but it does not
remove stale rows or give operators a bounded maintenance workflow.

This design adds an explicit maintenance API rather than implicit cleanup in `search()`. That keeps
request-time behavior predictable and makes deletion auditable by the caller.

## Public API Shape

Implementation names can be adjusted to fit local style, but the API must expose:

- `MemoryMaintenancePolicy`
  - `max_identity`
  - `max_preferences`
  - `max_context`
  - `compact_duplicates`
- `MemoryCompactionCandidate`
  - memory type
  - canonical memory id
  - duplicate memory ids
  - reason
- `MemoryMaintenanceSummary`
  - user id
  - dry-run flag
  - expired count
  - over-limit count
  - compacted count
  - deleted ids
  - compaction candidates
- `run_memory_maintenance(user_id, policy, dry_run=True)`

The API operates on exactly one `user_id`.

## Retention Rules

Retention is deterministic:

1. Expired `context` rows are eligible for deletion.
2. Per-type max counts are enforced by `updated_at DESC, id ASC`; newest rows are kept.
3. Over-limit older rows are eligible for deletion.
4. Deletions remove the row from `memory_items` and call `vector_store.delete(id, mem:{user_id})`.

Dry-run returns the same summary without mutating SQLite or vector-store.

## Compaction Rules

Compaction is intentionally conservative. This change does not ask an LLM to merge memories. It only
detects exact normalized duplicate content within the same user and same memory type:

- normalize by trimming and casefolding whitespace
- group duplicates by `(type, normalized_content)`
- canonical item is newest by `updated_at DESC, id ASC`
- duplicate ids are candidates for removal

When apply mode is enabled and `compact_duplicates=True`, duplicates are removed, leaving the
canonical item. The summary reports candidates either way.

## Isolation

Maintenance must never read or mutate other users' memories. Vector deletion namespace must always
be `mem:{user_id}`. The API does not accept tenant/global scope and does not create shared memory.

## Error Handling

- Empty `user_id` fails fast.
- Negative limits fail fast.
- Vector deletion failures should not silently hide row deletion behavior. For this spec, keep the
  operation simple: delete row, attempt vector delete, and let unexpected vector errors surface so
  callers can retry or run reindex.

## Testing

TDD slices:

- Public API/import tests.
- Dry-run tests proving no SQLite/vector mutation.
- Expired context apply tests.
- Per-type over-limit apply tests.
- Duplicate compaction candidate/apply tests.
- User isolation and vector namespace tests.

Relevant loop commands:

- `uv run pytest tests/unit/test_memory_retention_compaction.py -x -q`
- `uv run pytest tests/integration/test_memory_retention_compaction.py -x -q`
