## 0. 前置确认

- [ ] 0.1 确认 `knowledge-base-core` 已完成
- [ ] 0.2 确认默认 evaluation 不调用真实模型或外部服务
- [ ] 0.3 确认 evaluation 使用 tmp SQLite DB，不触碰 `data/`

## 1. Fixture schema

- [ ] 1.1 Write failing tests: fixture 包含 name、documents、queries、expected_chunks、forbidden_chunks
- [ ] 1.2 Write failing tests: invalid fixture 缺字段时 fail fast
- [ ] 1.3 实现 fixture schema / loader
- [ ] 1.4 运行 `uv run pytest tests/evaluation -x -q`

## 2. Vector-only retrieval evaluation

- [ ] 2.1 Write failing tests: runner ingest fixture documents 并执行 query
- [ ] 2.2 Write failing tests: expected chunk/snippet 必须命中 top-k
- [ ] 2.3 Write failing tests: forbidden chunk/snippet 不应命中
- [ ] 2.4 实现 deterministic evaluation runner
- [ ] 2.5 运行 `uv run pytest tests/evaluation -x -q`

## 3. Isolation and opt-in real provider

- [ ] 3.1 Write failing tests: evaluation 使用 tmp DB / tmp vector backend config
- [ ] 3.2 Write failing tests: real embedding evaluation 默认 skip
- [ ] 3.3 Write failing tests: 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 但缺少 provider credentials 时 skip
- [ ] 3.4 实现 isolation 和 real provider opt-in
- [ ] 3.5 运行 `uv run pytest tests/evaluation -x -q`

## 4. Docs and CI boundary

- [ ] 4.1 更新 `docs/capabilities/knowledge-base.md`
- [ ] 4.2 更新 CI quality gate spec，说明 KB evaluation 不进入默认 PR gate
- [ ] 4.3 运行 `uv run pytest -x -q`
- [ ] 4.4 运行 `uv run ruff format src tests`
- [ ] 4.5 运行 `uv run ruff check src tests`
- [ ] 4.6 运行 `uv run mypy src`
- [ ] 4.7 运行 `openspec validate knowledge-base-retrieval-evaluation`
