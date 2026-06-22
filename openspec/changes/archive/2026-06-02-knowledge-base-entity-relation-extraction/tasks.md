# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-entity-relation-extraction --strict`

## 2. Schema migration and models

- [x] 2.1 Write failing tests：Alembic upgrade 后存在 `kb_extraction_runs`、`kb_entities`、`kb_entity_mentions`、`kb_relations`，且 entity 唯一键为 `(tenant_id, kb_id, entity_type, normalized_name)`
- [x] 2.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 2.3 Implement：新增 Alembic migration 和 models / store skeleton
- [x] 2.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 2.5 Write failing tests：entity / relation type validation 只允许第一版固定类型
- [x] 2.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.7 Implement：补 dataclasses、type constants 和 validation
- [x] 2.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Normalization and entity upsert

- [x] 3.1 Write failing tests：同一 tenant + kb + type + normalized_name 合并，同名不同 KB 不合并
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 normalized name 和 entity upsert
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Deterministic extractor

- [x] 4.1 Write failing tests：deterministic extractor 从 fixture 抽取 customer、project、system、team、concept / term 等实体
- [x] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.3 Implement：实现 deterministic extractor
- [x] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing tests：deterministic extractor 抽取 depends_on、defines、conflicts_with 等 relation，并附 chunk evidence
- [x] 4.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.7 Implement：补 relation extraction
- [x] 4.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 5. Explicit extraction run service

- [x] 5.1 Write failing tests：`run_entity_extraction(tenant_id, kb_id, document_id=...)` 只扫描指定 document chunks，写入 run summary、entities、mentions、relations
- [x] 5.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.3 Implement：实现 document-level extraction run service
- [x] 5.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 5.5 Write failing tests：按 KB 全量 run 逐 document 执行，单 document 失败隔离并记录 failed count
- [x] 5.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.7 Implement：实现 KB-level extraction run
- [x] 5.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 6. Document-level replace semantics

- [x] 6.1 Write failing tests：document rerun 成功后替换该 document 旧 mentions / relations，保留 run summaries
- [x] 6.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 6.3 Implement：实现 document replace
- [x] 6.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 6.5 Write failing tests：document rerun 失败时不删除旧 active mentions / relations
- [x] 6.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 6.7 Implement：用事务保护 replace
- [x] 6.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 7. Public API and CLI

- [x] 7.1 Write failing tests：public API 可从 `fleetent.intelligence.knowledge_base` 导入 extraction models 和 `run_entity_extraction`
- [x] 7.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 7.3 Implement：导出 public API
- [x] 7.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 7.5 Write failing tests：`fleetent admin kb extract-entities --kb-id ... [--document-id ...]` 调用 explicit run 并输出脱敏 summary
- [x] 7.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 7.7 Implement：新增 admin CLI 命令
- [x] 7.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 8. LLM extractor opt-in smoke guard

- [x] 8.1 Write failing tests：未设置 `FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1` 时真实 LLM smoke skip
- [x] 8.2 Verify red：运行相关 evaluation / e2e smoke test 并确认失败
- [x] 8.3 Implement：新增 LLM extractor interface 和 opt-in smoke guard
- [x] 8.4 Verify green：运行相关 evaluation / e2e smoke test

## 9. Documentation

- [x] 9.1 Write failing tests：capability docs / roadmap 说明 entity extraction 已建立 schema 和 explicit run，但 graph search 仍未实现
- [x] 9.2 Verify red：运行相关文档测试或新增文档测试并确认失败
- [x] 9.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 `docs/capabilities/owner-capability-roadmap.md`
- [x] 9.4 Verify green：运行相关文档测试

## 10. 验证与归档

- [x] 10.1 运行 `uv run ruff format src tests`
- [x] 10.2 运行 `uv run ruff check src tests`
- [x] 10.3 运行 `uv run mypy src`
- [x] 10.4 运行 `uv run pytest -x -q`
- [x] 10.5 运行 `openspec validate 2026-06-02-knowledge-base-entity-relation-extraction --strict`
- [x] 10.6 运行 `git diff --check`
- [x] 10.7 所有 checkbox 完成后归档 change 并验证 `openspec/specs/knowledge-base/spec.md`
