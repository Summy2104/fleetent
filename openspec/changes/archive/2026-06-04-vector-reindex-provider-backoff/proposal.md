## Why

Real KB vector reindex with a Jina-compatible embedding provider exposed a production bug: the synchronous reindex executor sends embedding requests in a tight loop with no pacing or retry. A representative paced run indexed all 228 real KB chunks successfully, while the default full rebuild failed under provider rate limiting.

## What Changes

- Add bounded retry/backoff around each reindex upsert so transient provider failures can recover.
- Add a small injectable pacing hook between upserts so production reindex does not burst external providers.
- Preserve dry-run behavior, per-item failure isolation, and deterministic unit test behavior.

## Impact

- Owning package: `intelligence/vector_store`.
- Public API surface: `reindex()` behavior only; dataclass fields remain unchanged.
- Owned tables: none.
- Config namespace: none in this change.
- Cross-module dependencies: vector reindex continues to call vector runtime public API.
- Migration / shim plan: no migration.
