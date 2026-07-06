# kb-ingest-fail-closed — Tasks

> 每个实现 task 严格 TDD：先写测试（最窄命令 `uv run pytest <file>::<test> -x -q` 见红）→ 实现 → 同命令见绿。测试任务在对应实现任务之前。

## 1. store_document 原子化（embed-before-commit）

- [ ] 1.1 测试：embedding 抛错（stub `vector_store.embed_text` / 注入 backend 使 embed 失败）时 `store_document` 上抛异常，且库中**零残留**——document 列表无此文档、chunk 0、FTS 0、向量后端未收到任何 upsert/delete（integration，tmp_path KB 库，先红：旧代码 chunk 已提交）
- [ ] 1.2 测试：同身份 overwrite 场景下 embedding 失败 → 旧文档及其 chunk/向量保持原样可检索（先红）
- [ ] 1.3 实现：`ingest/runtime.store_document` 重排——先串行完成全部 chunk 向量化（内存持有），全部成功后才 `replace_document` + 删旧向量 + 用已算好的向量逐 chunk upsert（`_upsert_chunk` 相应改签名或新增带向量入参路径，兼顾 backend 注入与全局两分支）；见绿
- [ ] 1.4 回归：既有 ingest/检索测试无新增失败（`uv run pytest tests/integration -q -k "ingest or knowledge"`）

## 2. execute_sync_plan 吞错点改造

- [ ] 2.1 测试：单文件 ingest 抛错时——出现含 source path 的结构化异常日志（caplog/logger stub）、summary.errors 收集到脱敏错误文本、其余文件照常导入、failed 计数正确；errors 超上限截断（unit，先红）
- [ ] 2.2 测试：connector 异常文本含 token 形态（如 "token: xyz"）时 summary.errors 中已脱敏（先红）
- [ ] 2.3 实现：`sync_planner.py` 逐文件 except 改 `_logger.exception` + `redact_text` 收集；`SyncExecutionSummary` / `SyncResult` 增加 `errors` 字段（默认空、带上限常量）；见绿

## 3. worker 终态判定

- [ ] 3.1 测试：完败 summary（failed>0 ∧ ingested==0 ∧ scanned>0）→ job 落 failed、`last_error` 含首条错误摘要；部分失败 → done 且 `last_error` 携带明细摘要；全成功 → done 且 last_error 空（integration，复用既有 worker 测试夹具，先红）
- [ ] 3.2 实现：worker `sync_directory` / `connector_sync` 分支按 D3 判定（完败抛异常走既有 mark_failed；部分失败 done 时写 last_error——若 `mark_done` 不支持带 error，扩 `kb_ingest_jobs` 公共函数签名，不动表结构）；见绿
- [ ] 3.3 测试：dogfooding 端到端复现——embedding 后端不可用时入队 sync_directory + worker 消费 → job failed 带错、文档列表无此文档、`/status` 可读到错误（integration，先红→绿由 1/2/3 共同保证）

## 4. 收尾

- [ ] 4.1 更新 `docs/records/testing/kb-manual-test-playbook.md` §2 已知 bug 标注为已修（向量核查步骤保留为常规验证）；人工确认后提交
- [ ] 4.2 change/PR 收尾：`make test-pr` + `make test-integration-ci` 全绿（对照 main 基线无新增失败）
