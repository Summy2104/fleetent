## Why

KB 已收敛为"独立服务 + 平台控制面"，但命令侧还留着**缺失**与**冗余空壳**两类账（见 2026-07-01 命令目录审计）：

- **缺失**：standalone 侧能读能灌（`kb serve/worker/ingest/extract`）却**不能建库、不能重建索引**——`kb create` 只有 platform `POST /admin/kb`，`kb reindex` 根本没有。与"KB 可独立部署"方向冲突：无 platform 环境下建不了库。
- **冗余空壳**：`platform maintenance kb sync` 与 `platform maintenance vector reindex` 是 **no-op**（只记审计 trace、不干活）。真连接器同步早在 kb-worker（`connector_sync` job + sweep）；真向量重建在 `vector_store.reindex()`。这俩是 build-but-unwired 残留（同当初 `platform kb extract-entities`）。

本 change 只动**命令层**（不碰 HTTP API，⚡ 检索归属原则另议）：补齐 standalone `kb create` / `kb reindex`，退掉两个平台空壳。所有新命令用 `kb <verb>`（与刚落地的 kb-cli-verb-grouping 一致），纯 KB 服务侧、不依赖 platform。

## What Changes

- **新增 `fleetent kb create --config <kb-service.yaml> --kb <kb_id> [--description D]`**：standalone 建库，经配置解析 tenant/data_dir，调 `create_knowledge_base`（幂等 ensure）写本租户 `kb.db`，不依赖 platform。
- **新增 `fleetent kb reindex --config <kb-service.yaml> --kb <kb_id> [--wait]`**：**入队**一个 `reindex` job 到本租户 `kb_ingest_queue.db`，由 kb-worker 作为**唯一写者**消费执行——按该 KB 的向量命名空间从 `kb.db` 存量 chunk 重建 `kb_vectors.db`（经 `vector_store.reindex()` 公共 API）。`--wait` 轮询至终态并打印计数。**守单写者纪律**（与 ingest/extract 同形）。
- **kb-worker 新增 `reindex` job 类型**：在既有 job 分派（`import_document`/`sync_directory`/`connector_sync`/`extraction`）后加 `reindex` 分支，调 `vector_store.reindex()` 重建指定 KB 命名空间。
- **退役两个平台空壳**：删 `platform maintenance kb sync` 与 `platform maintenance vector reindex` 的 CLI 子命令、`platform/maintenance.py` 的 `run_kb_sync`/`reindex_vector` 函数、相关测试；`manual-maintenance-entrypoints` spec 的 "Vector rebuild" 场景移除（真重建改由 standalone `kb reindex`）。

**不做**（明确边界）：不碰任何 HTTP API（`/admin/kb/search`、检索归属等 ⚡ 项另议）；不加 `kb sync` 手动触发（kb-worker sweep 已自动同步，非必须）；非 KB 的通用向量 reindex（原平台空壳名义上覆盖但从未 work，无功能损失）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-standalone-ingest`：新增"手动建库命令 `kb create`"与"手动重建索引命令 `kb reindex`（入队、单写者）"两条要求（与既有"手动 ingest / extraction 命令"同族）。
- `kb-ingest-worker`：kb-worker 新增消费 `reindex` job 类型的要求（经 `vector_store` 公共 reindex API 重建指定 KB 向量命名空间，守单写者）。
- `manual-maintenance-entrypoints`：移除 "Vector rebuild"（platform admin CLI 跑向量重建）场景——该能力退役，真重建移至 standalone `kb reindex`；平台 `kb sync` 空壳一并退（真同步在 kb-worker）。

## Impact

- **代码（新增）**：`knowledge_base/` 下新增 `create_cli.py`、`reindex_cli.py`（沿用 ingest_cli/extract_cli 结构）；`__main__.py` 的 `kb` 分派加 `create`/`reindex`；`knowledge_base/worker.py` 加 `reindex` job 分支。
- **代码（删除）**：`platform/platform_cli/maintenance.py`（kb sync + vector reindex 子命令）、`platform/maintenance.py`（`run_kb_sync`/`reindex_vector`）、`tests/unit/test_coverage_closure_helpers.py` 相关断言。
- **spec**：`kb-standalone-ingest`（+2 requirement）、`kb-ingest-worker`（+reindex job）、`manual-maintenance-entrypoints`（−Vector rebuild 场景）。
- **无迁移、无 DB schema 变更、无 HTTP/wire 契约变更、无 `kb-service.yaml` 文件名变更**。
- 兼容：脚本若调 `platform maintenance vector reindex` 改用 `fleetent kb reindex`；`kb sync` 无替代（sweep 自动）。
