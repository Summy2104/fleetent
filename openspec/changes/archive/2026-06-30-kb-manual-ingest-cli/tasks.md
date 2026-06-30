## 1. LocalDirectoryDataSource 支持单文件（TDD）

- [x] 1.1 测试先行：`root_path` 指向单个受支持文件时,`fetch`/iter 只产出该文件;非支持后缀报错/跳过。见红
- [x] 1.2 实现：`connectors/local.py` 放宽 `is_dir` 约束——文件路径时退化为单文件迭代(保留 allowlist 校验)。见绿

## 2. 复活 sync_directory + CLI 入口（TDD）

- [x] 2.1 测试先行：调 `kb-ingest` CLI(或其 main 函数)对一个临时目录入队 → 断言 `kb_ingest_queue.db` 出现一条 `job_type="sync_directory"`、payload 含 abs path、tenant/kb 正确。见红
- [x] 2.2 实现 CLI：`knowledge_base/ingest_cli.py`(或 `cli.py`)——解析 `--config`/`--kb`/`<path>`/`--wait`;`load_kb_service_config` 取 tenant_id + `queue_database_url`;`_require_active_kb` 校验;`kb_ingest_jobs.enqueue_job(job_type="sync_directory", tenant_id, kb_id, connector_ref={"path": <abs>}, database_url=<queue>)`。见绿
- [x] 2.3 `__main__.py` 顶层加 `kb-ingest` 分发(与 `kb-worker`/`kb-serve` 同级)
- [x] 2.4 `--wait`：轮询该 job 状态至终态,打印 `scanned/ingested/skipped/failed`;超时提示检查 kb-worker。测试覆盖 wait 成功路径(mock/真 worker run_once）
- [x] 2.5 确认 `worker.py` 的 `sync_directory` 分支端到端可用(目录 → ingest → kb.db 出 document/chunk),补/留集成测断言其非孤儿

## 3. 单文件端到端 + KB 不存在报错

- [x] 3.1 集成测：`kb-ingest` 单文件 → worker drain → kb.db 出 1 个 document
- [x] 3.2 测试：`--kb` 指向不存在 KB → 命令清晰报错、不入队

## 4. example 连接器默认禁用

- [x] 4.1 `kb-service.yaml.example` 的 `drive-shared`/`confluence-shared` 改 `enabled: false`;更新相关断言测试(`test_packaged_config_templates` / `test_kb_service_init_config` 若断言 enabled）

## 5. 收尾门禁

- [x] 5.1 `openspec validate kb-manual-ingest-cli --strict`
- [x] 5.2 `make test-pr` + `make test-integration-ci` 全绿
- [x] 5.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [x] 5.4 功能分支 `openspec archive kb-manual-ingest-cli`（同步 kb-standalone-ingest spec）
- [x] 5.5 所有 checkbox 标 `[x]`
