## 0. 前置确认

- [ ] 0.1 确认本 change 只做 knowledge-base sync planner，不做第三方 connector
- [ ] 0.2 确认不新增 scheduler / queue / worker / admin API / dashboard
- [ ] 0.3 确认不新增 sync run / sync item 持久表，幂等性继续基于 `knowledge_source_states`
- [ ] 0.4 确认 source-side missing document 默认会删除对应 KB document

## 1. Planner public API shape

- [ ] 1.1 Write failing tests: `SyncAction`、`SyncPlan`、`SyncPlanItem`、summary dataclasses、`plan_local_directory_sync()` 和 `execute_sync_plan()` 可从 `fleetent.intelligence.knowledge_base` 导入
- [ ] 1.2 Write failing tests: 空目录 planner 返回空执行项和 scanned=0 summary
- [ ] 1.3 Implement: 新增 sync planner dataclasses、action names、`plan_local_directory_sync()`、`execute_sync_plan()` 和 public exports
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_sync_planner.py -x -q`

## 2. Local source planning

- [ ] 2.1 Write failing tests: 新文件生成 `ingest_new` plan item
- [ ] 2.2 Write failing tests: content hash 或 mtime 变化生成 `reingest_changed` plan item
- [ ] 2.3 Write failing tests: path、mtime、content hash 均未变化生成 `skip_unchanged` plan item
- [ ] 2.4 Write failing tests: unsupported 文件计入 `unsupported` summary，不进入可执行 ingest item
- [ ] 2.5 Implement: local directory planner compares source listing with `knowledge_source_states`
- [ ] 2.6 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_sync_planner.py -x -q`

## 3. Missing-source delete planning

- [ ] 3.1 Write failing tests: state 中存在但 source listing 缺失的文件生成 `delete_missing` plan item
- [ ] 3.2 Write failing tests: `delete_missing` item 包含原 document_id、source_id、tenant_id、kb_id 和 source_path
- [ ] 3.3 Implement: planner loads source state for the current source/tenant/kb and detects missing paths
- [ ] 3.4 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_sync_planner.py -x -q`

## 4. Plan execution

- [ ] 4.1 Write failing tests: `ingest_new` 执行 parser + `ingest_parsed()` 并成功后写入 source state
- [ ] 4.2 Write failing tests: `reingest_changed` 先删除旧 document，再 ingest 新 document，并更新 source state
- [ ] 4.3 Write failing tests: `delete_missing` 调用 `delete(document_id)` 并移除 source state
- [ ] 4.4 Write failing tests: `skip_unchanged` 不调用 parser、ingest 或 delete
- [ ] 4.5 Write failing tests: 单个 item 失败只计入 failed，不阻断其他 items
- [ ] 4.6 Implement: plan executor with idempotent per-item handling
- [ ] 4.7 Verify green: 运行 `uv run pytest tests/integration/test_knowledge_base_sync_planner.py -x -q`

## 5. Existing sync entry point

- [ ] 5.1 Write failing tests: `sync_local_directory()` 返回 summary 与 planner/executor 计数一致
- [ ] 5.2 Write failing tests: 连续两次 sync 第二次稳定返回 unchanged/skipped
- [ ] 5.3 Write failing tests: 删除本地文件后再次 sync 会删除 KB document，search 不再返回其 chunks
- [ ] 5.4 Implement: refactor `sync_local_directory()` to delegate to plan + execute
- [ ] 5.5 Verify green: 运行 `uv run pytest tests/integration/test_knowledge_base_sync_planner.py -x -q`

## 6. Docs and final verification

- [ ] 6.1 更新 `docs/capabilities/knowledge-base.md`
- [ ] 6.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 6.3 运行 `uv run ruff format src tests`
- [ ] 6.4 运行 `uv run ruff check src tests`
- [ ] 6.5 运行 `uv run mypy src`
- [ ] 6.6 运行 `uv run pytest -x -q`
- [ ] 6.7 运行 `openspec validate knowledge-base-sync-planner --strict`
- [ ] 6.8 运行 `git diff --check`
