# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 reflection spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-reflection-knowledge-base-reports --strict`

## 2. Models and persistence

- [x] 2.1 Write failing tests：public API 可导入 KB reflection report/finding models 和 `run_kb_reflection_report`
- [x] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.3 Implement：新增 models 和 public exports
- [x] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 2.5 Write failing tests：Alembic upgrade 后存在 `kb_reflection_reports`，payload 不保存 raw transcript
- [x] 2.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 2.7 Implement：新增 migration 和 persistence store
- [x] 2.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 3. Signal collection

- [x] 3.1 Write failing tests：KB reflection 只通过 observability public API 读取 traces/source attribution
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 observability signal adapter
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 3.5 Write failing tests：KB reflection 只通过 knowledge-base public API 读取 connector status、search / graph signals
- [x] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.7 Implement：实现 KB signal adapter
- [x] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Finding rules

- [x] 4.1 Write failing tests：zero-result / low attribution signals 生成 `missing_knowledge`
- [x] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.3 Implement：实现 missing knowledge rule
- [x] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing tests：failed/stale connector status 生成 `connector_sync_issue`
- [x] 4.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.7 Implement：实现 connector sync issue rule
- [x] 4.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.9 Write failing tests：低 score / 用户纠正 / source attribution 缺失生成 `low_retrieval_quality`
- [x] 4.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.11 Implement：实现 low retrieval quality rule
- [x] 4.12 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.13 Write failing tests：关系型 query 无 graph evidence 或 coverage 低生成 `entity_graph_gap`
- [x] 4.14 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.15 Implement：实现 graph gap rule
- [x] 4.16 Verify green：运行 `uv run pytest tests/unit -x -q`

## 5. Report runner and evaluation

- [x] 5.1 Write failing tests：`run_kb_reflection_report()` 输出 report、保存 report，并在 KB unavailable 时返回 insufficient signal
- [x] 5.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.3 Implement：实现 runner 和 persistence
- [x] 5.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 5.5 Write failing tests：deterministic evaluation 覆盖 expected / forbidden findings 和 payload redaction
- [x] 5.6 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [x] 5.7 Implement：新增 evaluation fixture / runner
- [x] 5.8 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 6. Documentation and verification

- [x] 6.1 Write failing tests：capability docs / roadmap 说明 KB reflection 只读报告，不自动写 KB 或触发 sync
- [x] 6.2 Verify red：运行相关文档测试
- [x] 6.3 Implement：更新 `docs/capabilities/reflection.md`、`docs/capabilities/knowledge-base.md` 和 roadmap
- [x] 6.4 Verify green：运行相关文档测试
- [x] 6.5 运行 `uv run ruff format src tests`
- [x] 6.6 运行 `uv run ruff check src tests`
- [x] 6.7 运行 `uv run mypy src`
- [x] 6.8 运行 `uv run pytest -x -q`
- [x] 6.9 运行 `openspec validate 2026-06-02-reflection-knowledge-base-reports --strict`
- [x] 6.10 运行 `git diff --check`
