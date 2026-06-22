## 1. schedule 字段（管理库 Alembic，TDD）

- [ ] 1.1 写测试（先红）：`tests/integration/` 中针对 `kb_connector_store`——写入/读出带 `sync_interval_seconds` + `last_scheduled_sync_at` 的 connector；默认两列为 NULL。先跑见红。
- [ ] 1.2 实现（绿）：新增 Alembic 迁移 `migrations/versions/<取 alembic heads 最新+1，别写死>_add_kb_connector_schedule.py`，给 `kb_connectors` 加 `sync_interval_seconds INTEGER` + `last_scheduled_sync_at TEXT`（均 nullable）。`kb_connector_store` 的 `_COLS` + 读写扩两列。见绿。

## 2. sync 历史表（KB core 嵌入式-Y，TDD）

- [ ] 2.1 写测试（先红）：sync 完成后 `knowledge_connector_sync_history` 追加一行；`list_connector_sync_history(connector_id, limit)` 按时间倒序返回多行。先跑见红。
- [ ] 2.2 实现（绿）：`knowledge_base/core/migrations.py` 版本号递增（`MIGRATIONS[-1][0]+1`，别写死），加表 `knowledge_connector_sync_history`。`operations.py` 在 `record_connector_status` 旁追加 history 写入 + 加 `list_connector_sync_history` 读 API。见绿。

## 3. 到期判定 + sweep 函数（TDD）

- [ ] 3.1 写测试（先红）：纯函数判定"哪些 connector 到期"——enabled 且 interval 非 NULL 且（last_scheduled_sync_at NULL 或 now-last≥interval）才到期；disabled / interval NULL / 未到期都不选。先跑见红。
- [ ] 3.2 写测试（先红）：sweep 行为——到期 connector 被 `enqueue_connector_job` 入队 + `last_scheduled_sync_at` 推进到 now；入队后同一 tick/间隔内不重复；单 connector 入队抛错时 sweep 继续其余、不抛出（舱壁化）。可 patch enqueue + store。先跑见红。
- [ ] 3.3 实现（绿）：在 platform 侧（`knowledge_base_management` 或 cron_scheduler 旁）实现 sweep 函数：查到期 → enqueue_connector_job → 推进 last_scheduled_sync_at，逐 connector try/except + log。见绿。

## 4. 接入 cron_scheduler（TDD）

- [ ] 4.1 写测试（先红）：sweep 被注册为 interval job（可断言 `add_interval_job` 被调用 / job id 存在）。先跑见红。
- [ ] 4.2 实现（绿）：在 `cron_scheduler`（`_register_maintenance_jobs` 或 lifespan）用 `add_interval_job(sweep, seconds=<基准 tick，默认 60>, job_id="__kb_connector_sync_sweep__")` 注册。基准 tick 可配（platform 设置）。见绿。

## 5. spec 文档对齐（archive 时同步）

- [ ] 5.1 `opsx:archive` 同步：新增 capability `kb-connector-scheduler`（delta 已在 change specs/ 下，archive 落到 openspec/specs/kb-connector-scheduler/）。

## 6. 收尾门禁

- [ ] 6.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [ ] 6.2 `make test-unit-ci` 通过（CI 覆盖率关 coverage --fail-under=76）。
- [ ] 6.3 跑相关测试：`uv run pytest tests/integration -q`（含 kb_connector_store / 迁移 / sweep / worker 相关，对照 main 基线无新增失败）。
- [ ] 6.4 `uv run python scripts/check_module_boundaries.py` 通过（确认 sweep 未落 agent runtime、无 agent→platform 反向依赖）。
- [ ] 6.5 merge 后、push 前跑 `uv run alembic heads` 确认**单一 head**；若并行 change 占了同号致多 head，把本迁移改号重链到对方之后（revision 改新号 / down_revision 指向对方），同步改文件名/测试，重跑迁移相关测试见绿再 push。
