## 1. Reindex retry and pacing

- [x] 1.1 Write failing tests: reindex retries one transient upsert failure before counting the item failed.
- [x] 1.2 Write failing tests: reindex applies an injectable per-item pacing hook after successful or failed item attempts.
- [x] 1.3 Implement bounded retry/backoff and pacing in vector reindex.
- [x] 1.4 Verify green: run `uv run pytest tests/unit/test_vector_store_reindex.py -x -q`.

## 2. Real validation

- [x] 2.1 Re-run related unit / integration tests.
- [x] 2.2 Re-run full real KB vector reindex against the local pilot KB.
- [x] 2.3 Update intelligence roadmap Go status with the resolved full reindex result.
- [x] 2.4 Run strict OpenSpec validation.
