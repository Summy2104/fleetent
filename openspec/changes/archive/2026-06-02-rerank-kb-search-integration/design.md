# Design

## Search Contract
`search()` keeps its current defaults:

```python
await search(query, tenant_id=None, kb_ids=None, limit=10, mode="vector", rerank=False)
```

`rerank=False` preserves current vector, keyword and hybrid behavior.

`rerank=True` is valid only when `mode="hybrid"`. This avoids pretending that a vector-only or
keyword-only result set has gone through the same candidate generation path as hybrid retrieval.

## Candidate Pool
Hybrid rerank uses a larger retrieval pool and then returns at most the requested `limit`:

```python
candidate_limit = min(max(limit * RERANK_CANDIDATE_MULTIPLIER, RERANK_CANDIDATE_MIN), RERANK_CANDIDATE_MAX)
```

If `limit <= 0`, search still returns an empty list without calling the rerank provider.

The constants live in knowledge-base runtime code because they are retrieval implementation policy, not
tenant/operator configuration for the first version.

## Rerank Mapping
The rerank provider receives candidate chunk content in original hybrid order and `top_n=limit`.

Provider results are interpreted as indexes into that candidate list:
- valid returned indexes are placed first in provider order;
- illegal indexes are ignored;
- duplicate indexes keep the first occurrence;
- candidates not returned by the provider are appended in original hybrid order until `limit` is reached.

For chunks selected by provider output, `KnowledgeChunk.score` is replaced with the provider rerank score.
For appended chunks, the original hybrid score is preserved.

## Failure Behavior
Rerank is a quality enhancement, not an availability dependency. If the provider is disabled, times out,
returns an explicit provider error or otherwise cannot produce results, knowledge-base search returns the
original hybrid ranking and emits a structured warning. If an existing runtime trace context is available,
the implementation should also emit a low-cost `kb_rerank_failed` event.

Provider protocol validation belongs in vector-store. Knowledge-base only handles provider failures and
defensive mapping of indexes.

## Evaluation
Default evaluation remains deterministic and offline. A fixture should prove that rerank can promote an
expected chunk above a distracting hybrid candidate and that forbidden chunks do not become top results.

Real rerank provider evaluation remains opt-in and must be skipped by default unless explicit environment
flags and credentials are present.
