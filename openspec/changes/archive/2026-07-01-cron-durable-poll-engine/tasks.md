## 1. 运行历史表与 store（#3 基础）

- [x] 1.1 写测试：agent_state 迁移追加后，新库 open 即含 `scheduled_task_runs` 表（列 id/task_id/fired_at/status/agent_error/delivery_error/duration_ms/kind/created_at），且 `user_version` 前进（integration）
- [x] 1.2 实现：`runtime/agent_state_migrations.py` `MIGRATIONS.append` 追加建 `scheduled_task_runs` 表（forward-only）
- [x] 1.3 写测试：`schedule_store` 运行历史读写——append 一行、按 task_id 列最近 N（倒序）、超过保留上限自动裁剪最旧、删除任务级联清历史（integration，tmp_path DB）
- [x] 1.4 实现：`schedule_store` 增 `record_run(...)` / `list_runs(task_id, limit)` / 保留裁剪；`delete` 连带删 `scheduled_task_runs`

## 2. next_run 计算（纯函数）

- [x] 2.1 写测试：`compute_next_run(kind, spec, base, tz)` 纯函数——interval= base+间隔；cron= 下一个匹配（用 CronTrigger 数学，DST/timezone 安全）；once= 固定；覆盖陈旧 base 快进到"下一个未来时刻"（unit）
- [x] 2.2 实现：`cron_scheduler` 内 `compute_next_run`（cron 复用 APScheduler `CronTrigger` 仅做 next-fire 计算，不用 AsyncIOScheduler；interval 从 last_run+间隔）

## 3. 轮询引擎：到期选择 + 执行前先推进 + claim

- [x] 3.1 写测试：到期选择——`next_run_at<=now` 且 enabled 的任务被选中、未来的不选（integration）
- [x] 3.2 写测试：执行前先推进（D2/D3）——claim 用条件 UPDATE（`WHERE id AND next_run_at=old`），仅 rowcount==1 dispatch；模拟重叠 claim 只成功一次（同一 occurrence 不双触发）；`once` 不推进（integration）
- [x] 3.3 写测试：慢任务不漏触发——interval 任务单次运行时长 > interval 时，`next_run_at` 已在运行前推进，后续 tick 仍能触发下一 occurrence（不被吞）（integration，mock LLM 慢返回）
- [x] 3.4 写测试：陈旧快进——`next_run_at` 落后多个周期时快进到下一未来时刻，至多补触发一次（integration）
- [x] 3.5 实现：引擎的 due 查询、claim（条件推进）、`compute_next_run` 接入、陈旧快进；`once` 不推进

## 4. tick 循环 + 有界并行 + 生命周期

- [x] 4.1 写测试：有界并行——多任务同 tick 到期时按信号量上限并发；慢任务不阻塞其它任务触发；超过上限的排队（integration）
- [x] 4.2 写测试：tick 生命周期——`start()` 起后台 tick 任务、`shutdown()` 干净取消不泄漏；`scheduling.enabled=false` 不起 tick（integration）
- [x] 4.3 实现：`CronScheduler.start/shutdown` 改为起停 asyncio tick 后台任务；tick 内 due→claim→`asyncio.create_task(_fire, sem)` 有界并行；移除 AsyncIOScheduler
- [x] 4.4 实现：`_register_maintenance_jobs`（spillover cleanup 等）迁为 tick 引擎内部固定周期任务，去除 APScheduler 残留

## 5. _fire 收尾写历史 + 不静默丢

- [x] 5.1 写测试：`_fire` 收尾——ok/error 各写一行历史，agent 错误与投递错误分列；投递失败但 run 成功 → status=error 且 delivery_error 非空、agent_error 空；写历史失败只 log 不崩、不改 fire 结果（integration）
- [x] 5.2 写测试：不可运行的到期 occurrence（principal 复核 skip）记 `skipped` 历史，不静默消失（integration）
- [x] 5.3 实现：`_fire`/`_record_run` 追加 `record_run` 历史写（best-effort），principal skip 分支记 `skipped`；保留既有 `update_run_state` 与 trace

## 6. schedule 工具 history 动作（#3 出口）

- [x] 6.1 写测试：`schedule(action="history", task_id)` 返回最近运行（时间/状态/错误/耗时）；未知 task_id 返回清晰 error 字符串不抛（unit，mock cron_scheduler/list_runs）
- [x] 6.2 实现：`tools/builtin_tools.py` `schedule` 增 `history` 分支 + docstring/参数说明；模块 facade 暴露 `list_runs`

## 7. 配置项

- [x] 7.1 写测试：`SchedulingSettings` 新增 tick 周期/执行并发/历史保留条数，缺省回落安全默认；引擎读取生效（unit）
- [x] 7.2 实现：`config.py` `SchedulingSettings` 增字段（tick_interval_seconds/max_parallel/history_retention），引擎/store 读取

## 8. 首启回填 + 公共 API 不回归

- [x] 8.1 写测试：首次 `start()` 为缺 `next_run_at` 的既有任务回填一次；create/list/remove/run_now/pause/resume 语义与返回不回归（integration）
- [x] 8.2 实现：`start()` 回填缺失 `next_run_at`；确认 facade 签名/行为不变

## 9. 收尾验证

- [x] 9.1 护栏：`cron_scheduler`/`schedule_store`/历史模块无 `import fleetent.platform.*`，不碰 platform 表（`test_module_dependency_guardrails` 绿）
- [x] 9.2 依赖：确认无其它模块用 APScheduler 后，从 `pyproject.toml` 移除 apscheduler（若仅 CronTrigger 数学仍需则保留并注明）；`make test-pr` + `make test-integration-ci` 全绿（仅已知本地假失败）
