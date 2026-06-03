# Rerank KB Search Integration

## Why
Knowledge-base search already has vector, keyword and hybrid modes, and vector-store already exposes a
rerank provider abstraction. The two are not connected yet: hybrid search returns fused candidates only,
so real rerank evaluation cannot validate the production retrieval path.

This change integrates rerank into knowledge-base hybrid search as an explicit opt-in, while keeping
current search behavior unchanged by default.

## What Changes
- Add `rerank: bool = False` to the knowledge-base `search()` API.
- Allow rerank only for `mode="hybrid"`; fail fast for vector or keyword rerank requests.
- When rerank is enabled, gather a larger hybrid candidate pool before calling the configured rerank
  provider.
- Keep candidate pool sizing as code constants, not configuration:
  - `RERANK_CANDIDATE_MULTIPLIER = 5`
  - `RERANK_CANDIDATE_MIN = 20`
  - `RERANK_CANDIDATE_MAX = 100`
- Fall back to original hybrid ordering when the rerank provider is disabled or fails.
- Ignore illegal provider indexes and append missing candidates after reranked candidates in original
  hybrid order.
- Add deterministic unit, integration and evaluation coverage for reranked KB retrieval.

## Out Of Scope
- Rerank for vector-only or keyword-only search.
- Query planner, graph search integration or multi-hop retrieval.
- New rerank configuration fields.
- Replacing hybrid search default behavior.
- Real rerank provider tests in default CI.

## Module Boundary Impact
- Owning package: `fleetent.intelligence.knowledge_base`.
- Public API surface: `search(..., rerank: bool = False)`.
- Owned tables: none.
- Config namespace: no new namespace or field; this uses existing `rerank.*` settings.
- Cross-module dependencies: knowledge-base may use the public `fleetent.intelligence.vector_store`
  rerank provider boundary and existing observability/logging boundaries.
- Migration / shim plan: no DB migration and no import shim required.
