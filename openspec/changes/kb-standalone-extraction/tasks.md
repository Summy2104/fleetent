## 1. extraction_enabled setter（TDD）

- [ ] 1.1 测试先行：`KnowledgeStore` 加 `set_extraction_enabled(tenant_id, kb_id, bool)`——对存量 KB 置真/假,`is_extraction_enabled` 读到新值。见红
- [ ] 1.2 实现：`core/store.py` 加 setter（`UPDATE knowledge_bases SET extraction_enabled = :v WHERE tenant_id/kb_id`，named params）。见绿

## 2. kb-extract CLI（TDD）

- [ ] 2.1 测试先行：`kb-extract --config <yaml> --kb <id>` → 置 extraction_enabled=true + 对每个存量 doc(`list_documents`)入队一个 `extraction` job(`connector_ref={"document_id": id}`)到本租户队列;KB 不存在 → 报错不入队。见红
- [ ] 2.2 实现 CLI(`knowledge_base/extract_cli.py` 或复用 ingest_cli 模式)：`load_kb_service_config` 取 tenant/queue;`_require_active_kb`;`set_extraction_enabled(true)`;遍历 `list_documents` → `kb_ingest_jobs.enqueue_job(job_type="extraction", tenant_id, kb_id, connector_ref={"document_id": id}, database_url=queue)`。见绿
- [ ] 2.3 `__main__.py` 顶层加 `kb-extract` 分发（与 kb-ingest/kb-worker/kb-serve 同级）
- [ ] 2.4 `--wait`：轮询 extraction job 至终态,打印 documents/entities/relations 计数;超时提示查 kb-worker

## 3. 抽取模型 example 预置

- [ ] 3.1 `kb-service.yaml.example` 的 `extraction` 段预置：`enabled: false`、endpoint 指向本地/自托管抽取模型(如 `http://127.0.0.1:11434/v1/`)、model 占位（如 qwen3:8b）；更新相关断言测试

## 4. e2e 验证（graph 端到端）

- [ ] 4.1 集成测：建 KB → 开 extraction → ingest（或回填）→ 断言 `kb_entities`/`kb_relations` 被填 → 以 `use_planner=true` 检索命中实体关联 chunk（可用 deterministic 抽取器避免真 LLM，参照现有 extraction 测试）

## 5. 收尾门禁

- [ ] 5.1 `openspec validate kb-standalone-extraction --strict`
- [ ] 5.2 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 5.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [ ] 5.4 功能分支 `openspec archive kb-standalone-extraction`（同步 kb-standalone-ingest spec）
- [ ] 5.5 所有 checkbox 标 `[x]`
