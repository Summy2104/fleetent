# Tasks: kb-standalone-create-reindex

> 纯命令层：加 standalone `kb create`/`kb reindex`、退平台两个 no-op 空壳。不碰 HTTP API。
> 新命令走 `kb <verb>`（对齐已落地 kb-cli-verb-grouping）。TDD Hard Gate：测试在实现前，最窄命令红→绿。

## 1. `kb create`（standalone 建库）

- [ ] 1.1 [test-red] 加 `tests/integration/test_kb_create_cli.py`：写 `kb-service.yaml` → 运行 `create_cli.main(["--config", ..., "--kb", "kb-a"])` → 断言本租户 `kb.db` 出现该 KB；再跑一次断言幂等(no-op 成功)。跑 `uv run pytest tests/integration/test_kb_create_cli.py -x -q` → **见红**（模块不存在）。
- [ ] 1.2 [impl] 新增 `src/fleetent/knowledge_base/create_cli.py`（沿用 `ingest_cli.py`/`extract_cli.py` 结构：`load_kb_service_config` → tenant_id/data_dir → `_knowledge_database` → `create_knowledge_base(tenant_id, kb_id, description, database=db)`，幂等）；`__main__.py` 的 `kb` 子命令分派加 `create` → `create_cli.main(argv[2:])`。跑同命令 → **见绿**。

## 2. `kb reindex`（入队）+ kb-worker reindex handler

- [ ] 2.1 [test-red] 加 worker 测试：入队一个 `reindex` job（tenant/kb_id）→ 运行 worker 处理 → 断言经 `vector_store.reindex()`（可 monkeypatch/spy）重建该 KB 命名空间。跑 `uv run pytest tests/integration -k "worker and reindex" -x -q` → **见红**（`unknown kb ingest job type: reindex`）。
- [ ] 2.2 [impl] `knowledge_base/worker.py`：在 job 分派链末（`extraction` 之后、`raise unknown` 之前）加 `if job_type == "reindex":` 分支——由 job 的 `tenant_id`/`kb_id` 构造 `ReindexRequest` 并调 `vector_store.reindex()`。**关键：namespace 必须与 ingest 写该 KB 向量时的命名空间一致**——先读 ingest 侧（`knowledge_base/ingest/runtime.py` + `vector_store/namespaces.py`）确认 KB 向量的 owner/namespace 方案，reindex 用同一方案；source items = 该 KB 在 `kb.db` 的存量 chunk。跑 2.1 → **见绿**。
- [ ] 2.3 [test-red] 加 `tests/integration/test_kb_reindex_cli.py`：`reindex_cli.main(["--config", ..., "--kb", "kb-a"])` → 断言入队一个 `reindex` job；KB 不存在时报错不入队；`--wait` 轮询终态。跑 → **见红**。
- [ ] 2.4 [impl] 新增 `src/fleetent/knowledge_base/reindex_cli.py`（沿用 `extract_cli.py`：校验 KB 存在 → `enqueue_job(job_type="reindex", tenant_id, kb_id, database_url=queue_url)` → `--wait` 复用轮询工具）；`__main__.py` 的 `kb` 分派加 `reindex`。跑 2.3 → **见绿**。
- [ ] 2.5 [test] e2e/集成：ingest 若干 chunk → 清/损坏 `kb_vectors.db` → `kb reindex --wait` → 检索仍命中（证明重建 namespace 与 ingest 对齐）。

## 3. 退平台两个 no-op 空壳

- [ ] 3.1 [test-red] 改 `tests/unit/test_coverage_closure_helpers.py`（及其它引用）：断言 `platform maintenance kb sync` / `vector reindex` **不再存在**，移除对 `run_kb_sync`/`reindex_vector` 的断言。跑相关单测 → **见红**（命令/函数仍在）。
- [ ] 3.2 [impl] 删 `platform/platform_cli/maintenance.py` 的 `kb sync` 与 `vector reindex` 子命令注册与 handler 分支；删 `platform/maintenance.py` 的 `run_kb_sync` / `reindex_vector`。跑同命令 → **见绿**。
- [ ] 3.3 grep 确认无残留：`grep -rn "run_kb_sync\|reindex_vector\|maintenance kb sync\|maintenance.*vector.*reindex" src tests` 仅剩必要（无死引用）。

## 4. 收尾门禁（全绿才算完）

- [ ] 4.1 grep 校验：`grep -rn "fleetent kb create\|fleetent kb reindex" -r`（新命令在 docs/help 中一致引用）；旧空壳零残留（见 3.3）。
- [ ] 4.2 `openspec validate kb-standalone-create-reindex --strict`
- [ ] 4.3 `uv run mypy src`
- [ ] 4.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"（含新增的 create/reindex 测试 + worker reindex + 退空壳的 maintenance 测试）。
- [ ] 4.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（新命令在 knowledge_base/ 不 import platform；worker reindex 用 vector_store 公共 API）。
- [ ] 4.6 手验：`uv run fleetent kb create --config <yaml> --kb t1` 建库；`uv run fleetent kb reindex --config <yaml> --kb t1 --wait`（kb-worker 在跑时）打印重建计数；`uv run fleetent platform maintenance vector reindex` 报未识别。
- [ ] 4.7 tasks.md 全 `[x]`；功能分支 `openspec archive kb-standalone-create-reindex`（同步 kb-standalone-ingest + kb-ingest-worker + manual-maintenance-entrypoints 三 spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
