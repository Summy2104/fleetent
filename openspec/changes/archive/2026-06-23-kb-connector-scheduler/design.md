## Context

KB connector sync 现状（grounding 2026-06-23）：

- **触发**：`kb_ingest_jobs` 队列 + `knowledge_base/worker.py` 消费。`connector_sync` job → `run_connector_sync(connector_id, settings, dry_run)`（`operations.py:178`，返回 `ConnectorSyncResult{connector_id, status, summary, error}`）。入队经 `kb_ingest_jobs.enqueue_connector_job(connector_row)`。当前只有 admin API / CLI 手动入队。
- **connector 定义**：`kb_connectors` 表在**管理库**（`kb_connector_store` 用 `create_database(Settings().database_url)`；迁移 076 只 drop 了 `knowledge_connector_status`、kb_connectors 留在管理库）。列：`connector_id, kind, enabled, tenant_id, kb_id, config, custom, created_at, updated_at`。无 schedule 字段。
- **状态**：`knowledge_connector_status` 在 **KB core 嵌入式-Y**（`core/migrations.py:115`），`ON CONFLICT(connector_id) DO UPDATE` = 每 connector 一行 last status。`record_connector_status` 写它。无历史多行。
- **cron**：`cron_scheduler.CronScheduler`（top-level，platform lifespan 启动）已有 `_register_maintenance_jobs()` 范式 + `add_interval_job(func, seconds, job_id)` 现成接口。

## Goals / Non-Goals

**Goals:**
- per-connector opt-in 周期调度；到期由 platform cron 自动入队 sync job（复用现成队列+worker）。
- 轻量重试恢复 + 入队去重（不重复堆积 job）。
- 多行 sync 历史，可观测过去几次定时 sync。

**Non-Goals:**
- cron 表达式（用 interval 秒）；webhook（②）；幂等锁/多 worker 协调；改 worker / run_connector_sync 逻辑。

## Decisions

**D1 · schedule 字段（Alembic，管理库）**。`kb_connectors` 加两列：
- `sync_interval_seconds INTEGER`（NULL = 不调度 = 默认 opt-out；正整数 = 每 N 秒一次）
- `last_scheduled_sync_at TEXT`（ISO 时间，NULL = 从未；到期判定 + 去重用）

迁移号 apply 时取 `alembic heads` 最新值 +1，**不写死**（并行 change 可能占号）。`kb_connector_store` 读写、`_COLS` 扩两列。

**D2 · 调度 sweep（platform cron_scheduler）**。在 `cron_scheduler` 注册一个 interval job（基准 tick，默认 60s、可配），sweep 函数：
1. 查 `kb_connectors` where `enabled=1 AND sync_interval_seconds IS NOT NULL`；
2. 对每个，若 `last_scheduled_sync_at IS NULL` 或 `now - last_scheduled_sync_at >= sync_interval_seconds` → 到期；
3. 到期者：`enqueue_connector_job(row)` + **立即把 `last_scheduled_sync_at` 推进到 now**（主去重，见 D3）；
4. sweep 整体 best-effort：单 connector 入队失败只记日志、不影响其它（舱壁化）。

sweep 注册点：`_register_maintenance_jobs` 内加一条，或 lifespan 显式 `add_interval_job`。基准 tick 决定调度精度上限（实际 interval 向上取整到 tick）。

**D3 · 轻量去重 + 恢复**。
- **去重主手段 = 入队即推进 `last_scheduled_sync_at`**：下个 tick 在 interval 内算不到期 → 不重复入队。即使 sync 比 interval 慢导致偶发并入，worker 队列串行执行、不破坏正确性。
- **恢复**：sync 失败由 worker 记 status + history（status=sync_failed/auth_failed）。调度层**不读状态决定重试**——下次到期 tick 照常入队即天然重试（轻量、无状态机）。
- （可选加强，本单可不做）入队前查该 connector 是否已有 pending `connector_sync` job 以跳过——若实现简单则加，否则靠 D3 的时间推进去重已足够。

**D4 · sync 历史（KB core 嵌入式-Y）**。`core/migrations.py` 版本号递增，新增多行表
`knowledge_connector_sync_history`（`id, connector_id, tenant_id, kb_id, status, summary_json, error, started_at, finished_at`）。
在 `record_connector_status`（或其调用处 operations.py:617）旁追加一行 history（last-row 表保留不动，二者并存）。
提供 `list_connector_sync_history(connector_id, limit)` 读 API。

## Risks / Trade-offs

- **双迁移面**：Alembic（管理库）+ 嵌入式-Y（KB core）各加一处。两者独立、互不依赖；apply 时 Alembic 迁移号取最新、嵌入式-Y 版本号取 `MIGRATIONS[-1][0]+1`，都别写死。合并后跑 `alembic heads` 确认单 head。
- **基准 tick vs 精度**：interval 实际向上取整到 tick（默认 60s）。对"每日/每小时轮询"足够；要秒级精度不适用（也不该用轮询调度做秒级）。tick 设短会增加空 sweep 频率，设默认 60s 平衡。
- **慢 sync 偶发并入**：interval ≫ sync 时长时几乎不发生；真发生时 worker 串行消费、结果是多跑一次 sync，不破坏数据（sync 本身幂等于内容 diff）。可接受，符合"轻量"。
- **sweep 必须舱壁化**：单 connector 查询/入队异常不得中断整个 sweep、不得让 cron job 抛出（参照 reflection auto-apply 的 best-effort 范式）。
- **边界**：sweep 跑在 platform 进程、读管理库 kb_connectors、入队——全 platform/ingest 侧，零 agent runtime 触碰。务必不要把 sweep 误放进 agent runtime 模块。
