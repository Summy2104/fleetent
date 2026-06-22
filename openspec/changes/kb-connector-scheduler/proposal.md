## Why

KB connector sync 目前**只能手动触发**（admin API / CLI 入队 `connector_sync` job → worker drain）。on-prem 客户的增量摄取主路径应是**定时轮询**（webhook 是 opt-in，且纯内网够不到公网 callback——见 [[kb-production-gaps-plan]] 判断 2）。这是 KB 四个生产化缺口里最后一个未做的（③ audit、④ eval-obs 已落地，② webhook deferred）。

现缺：
- connector 没有"按周期自动 sync"的能力；运营者得人工点。
- 只有 `knowledge_connector_status`（每 connector 一行 last status），**没有历史多行**——无法看"过去几次定时 sync 跑没跑、失败没失败"。

现在做：给 connector 加 opt-in 的周期调度，platform 的 `cron_scheduler` 周期性把到期 connector 入队（复用现成 `kb_ingest_jobs` 队列 + worker），并补一张多行 sync 历史表。纯 platform/ingest 侧，不碰 agent runtime。

## What Changes

- **schedule 字段（管理库 Alembic）**：`kb_connectors` 新增 `sync_interval_seconds INTEGER NULL`（NULL = 不调度 = **默认 opt-out**，设值即 opt-in）+ `last_scheduled_sync_at TEXT NULL`（到期计算 + 去重用）。
- **调度 sweep（platform cron_scheduler）**：复用 `CronScheduler.add_interval_job`，注册一个基准 tick（默认 60s，可配）的 sweep：查 `kb_connectors` 中 `enabled` 且 `sync_interval_seconds` 非 NULL 且**已到期**（`now - last_scheduled_sync_at >= interval`）的 connector → `kb_ingest_jobs.enqueue_connector_job` 入队 → 同步推进 `last_scheduled_sync_at`。worker（现成）drain 执行 `run_connector_sync`。
- **轻量去重 + 恢复**：入队即推进 `last_scheduled_sync_at` → 下个 tick 在 interval 内不会重复入队（主去重）；失败的 sync 由 worker 记 status/history，**下次到期 tick 自然重试**（不做幂等锁 / 多 worker 协调——队列已串行）。
- **sync 历史多行表（KB core 嵌入式-Y）**：新增 `knowledge_connector_sync_history`（connector_id, status, summary_json, error, started_at, finished_at），每次 sync 结果追加一行（与现有 last-row `knowledge_connector_status` 并存）。

**明确不做**：
- cron 表达式语法——本单用 interval 秒（更简单、与 `reflection.interval_seconds` 一致），cron 表达式 deferred。
- webhook 推送触发（② 缺口，deferred、数据主权）。
- 幂等锁 / 多 worker 分布式协调（轻量恢复够用）。

## Capabilities

### New Capabilities
- `kb-connector-scheduler`: per-connector opt-in 周期调度，platform cron sweep 入队 sync job + 多行 sync 历史 + 轻量重试恢复。

### Modified Capabilities
（无）

## Impact

- **owning package**：`platform/knowledge_base_management/`（kb_connector_store schedule 字段 + sweep）、
  `cron_scheduler`（注册 sweep）、`knowledge_base/`（core migration 加 history 表 + operations 写 history）
- **public API surface**：`kb_connector_store` schedule 读写；新 sweep 函数；`knowledge_connector_sync_history` 表 + 其 record/list 函数
- **owned tables**：
  - `kb_connectors`（管理库 / **Alembic**，+`sync_interval_seconds`、+`last_scheduled_sync_at` 两列）
  - `knowledge_connector_sync_history`（KB core / **嵌入式-Y** `knowledge_base/core/migrations.py`，新表）
- **config namespace**：platform 侧 sweep 基准 tick 间隔（可选配置，默认 60s）
- **cross-module dependencies**：sweep（platform）读 `kb_connectors`（管理库）+ `enqueue_connector_job`（kb_ingest_jobs）——
  全 platform/ingest 侧；`run_connector_sync` 在 worker 跑；**不碰 agent runtime、无 agent→platform 反向依赖**
- **migration / shim**：**双迁移**——Alembic（管理库，head 当前 100，新迁移号 apply 时取最新别写死）+ KB core 嵌入式-Y 版本号递增。两者独立。
- **受影响代码**：`src/fleetent/platform/knowledge_base_management/kb_connector_store.py`、`src/fleetent/cron_scheduler.py`、
  `src/fleetent/knowledge_base/core/migrations.py`、`src/fleetent/knowledge_base/operations.py`、
  `migrations/versions/<新号>_*.py` + 相关单测/集成测试
