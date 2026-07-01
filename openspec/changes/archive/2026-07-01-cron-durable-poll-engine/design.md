## Context

`cron_scheduler.py` 现用 APScheduler `AsyncIOScheduler`，在 agent 单进程事件循环上注册内存触发器。`generate`/`action` 任务在 `_fire` 内联 `await agent_loop.run(...)`（LLM 单次 10~60s+）。job 配置 `max_instances=1 + coalesce=True + misfire_grace_time=3600`：当运行时长 ≳ interval，后续 tick 撞 `max_instances=1` 判 missed、再被 coalesce 合并 → 触发时刻被静默丢弃（AAA-8209 症状②）。运行状态仅 `schedule_store.update_run_state` 覆盖单行 `last_*`，无逐次历史（症状③）。

`scheduled_tasks` 是 agent 侧表（agent_state.db 嵌入式 forward-only 迁移，`runtime/agent_state_migrations.py` 用 `MIGRATIONS.append((prev+1, sql))` 递增）。调度器 agent 侧、无 platform import；`server.py` lifespan 经 `set_principal_resolver` 注入 platform 侧创建者复核（解耦 seam，本 change 不动）。接线：`runtime/agent_app.py` 构造 `CronScheduler(connectors_resolver=...)` 并 `await start()`。

参考 Hermes（`NousResearch/hermes-agent` `cron/`）：持久 `next_run_at` + `tick()` 轮询 + `advance_next_run()` 执行前先推进 + `get_due_jobs()` 陈旧快进 + `save_job_output()` 逐次落盘 + 有界并行。Hermes 用文件锁做跨进程互斥——fleetent 单进程不需要。

## Goals / Non-Goals

**Goals:**
- 用「持久 `next_run_at` + 轻量 asyncio tick 轮询 + 执行前先推进」引擎替换 APScheduler，根治短周期任务静默漏触发。
- 调度节奏与单次运行时长解耦；at-most-once（崩溃不重放同一 occurrence）。
- 陈旧计划快进，重启不爆发补发。
- 有界并行执行替代强制串行。
- 逐次运行历史（agent 错误/投递错误分离）+ `schedule history` 查询出口 + 保留上限。
- 公共 API 与三类型（notify/generate/action）语义、投递契约、principal 注入 seam **零回归**。

**Non-Goals:**
- 跨进程文件锁 / 独立 daemon（单进程不需要）。
- 定时任务管理 UI（#3 仅 schedule 工具出口，已与用户确认）。
- "第N次计数注入消息内容"（已判定不做）。
- 改动 platform 侧 `set_principal_resolver` 契约、notify/generate/action 投递语义。

## Decisions

### D1: 轮询引擎 vs 保留 APScheduler
**选**：自建轻量 tick 轮询（agent 进程内一个 asyncio 后台任务，周期 `sleep(tick_interval)` → 扫描到期任务）。
**理由**：APScheduler 的 `max_instances=1 + coalesce` 正是静默漏触发的机制根源；其 in-memory trigger 与"持久 next_run_at + 先推进"范式不契合。轮询引擎让"下次何时触发"完全由持久 `next_run_at` 决定，与单次运行时长无关。
**弃**：保留 APScheduler 改用非阻塞 dispatch —— 仍受其 misfire/coalesce 语义牵制，且要绕过其调度模型，复杂且脆弱。

### D2: 执行前先推进 next_run（at-most-once）
到期 recurring 任务在**执行前**、在 claim 的并发保护内先把 `next_run_at` 推进到下一 occurrence，再 dispatch 运行。`interval` 下一次 = `max(now, prev_next_run) + interval`（避免快速连补）；`cron` 下一次 = 从当前时刻算下一个匹配。`once` 不推进（保留重启重试至 completed）。
**理由**：这是解耦节奏与时长的关键，也保证同一 occurrence 崩溃不重放。
**权衡**：at-most-once 意味着极端情况下可能丢一次执行（优于崩溃循环连发几十次，Hermes 同款取舍）。

### D3: 到期选择 + claim 的并发保护（单进程）
tick 里：查 `next_run_at <= now` 的 enabled 任务 → 对每个任务在 `next_run_at` 上做**条件推进**（`UPDATE ... SET next_run_at=:new WHERE id=:id AND next_run_at=:old`，rowcount==1 才算 claim 成功），claim 成功者才 dispatch。
**理由**：条件 UPDATE 天然幂等，防止重叠 tick（或 `run_now` 并发）对同一 occurrence 双触发；单进程内无需文件锁。
**弃**：内存锁/asyncio.Lock —— DB 条件更新更可靠且对 `run_now` 手动触发也安全。

### D4: 有界并行执行
用 `asyncio.Semaphore(concurrency)` 包裹每次 `_fire` dispatch（`asyncio.create_task` + 信号量）。tick 不 `await` 单次 run 完成，继续扫描/推进其它到期任务。
**默认**：并发上限取一个安全默认（如 4），`SchedulingSettings` 可配。
**理由**：慢/挂起的 run 不阻塞其它任务与后续 tick；上限防止 LLM 运行堆积打爆资源。

### D5: 运行历史存储（#3）
agent_state.db 新增 `scheduled_task_runs(id, task_id, fired_at, status, agent_error, delivery_error, duration_ms, kind, created_at)`，`task_id` 外键随任务删除级联清理；每任务保留最近 N 行（写后按 `task_id` 裁剪）。`_fire` 收尾除 `update_run_state` 外追加一行历史；写历史 best-effort（失败只 log，不改 fire 结果、不崩调度）。`status ∈ {ok,error,missed,skipped}`，agent 错误与投递错误分列。
**理由**：正是 R.Alpha 无法回答"触发几次/每次结果"的缺口；错误分列区分"agent 失败"与"投递失败"。

### D6: schedule 工具 history 动作
`schedule(action="history", task_id=...)` 返回该任务最近 N 次运行（时间/状态/错误/耗时）。未知 task_id 返回清晰 error 字符串，不抛。
**理由**：agent（Slack/对话）即可自助查询，无需 UI。

### D7: 公共 API 与接线不变
模块 facade（`create_task`/`remove_task`/`set_task_enabled`/`run_task_now`/`list_tasks`）签名与语义不变；`CronScheduler(settings, connectors_resolver)` 构造与 `start()`/`shutdown()` 契约不变（内部 `start()` 改为启动 tick 任务、`shutdown()` 取消它）。`set_principal_resolver`、`_resolve_cron_principal`、`_fire` 的 notify/generate/action 分支与投递逻辑**原样保留**，仅把"何时调用 `_fire`"从 APScheduler 回调改为 tick 到期 dispatch，并在 `_fire` 前做推进、收尾写历史。
**理由**：最小化爆炸半径，三类型语义/投递/解耦契约零回归。

### D8: 迁移与依赖
`agent_state_migrations.py` `MIGRATIONS.append` 追加建 `scheduled_task_runs` 表（forward-only）。`scheduled_tasks` 已有 `next_run_at` 列，直接复用（引擎首次 `start()`/create 时为缺失 `next_run_at` 的任务回填一次）。APScheduler 在本模块内移除使用；确认无其它使用方后从依赖清单移除（`maintenance_spillover_cleanup` 等 `add_interval_job`/`_register_maintenance_jobs` 也一并迁到 tick 引擎的内部周期任务）。

## Risks / Trade-offs

- **[at-most-once 丢一次]** 极端场景（推进后、运行前崩溃）丢该次执行 → 可接受，远优于崩溃连发；历史记 `missed`/无记录由下次 tick 快进纠正。
- **[tick 精度 = tick_interval]** 触发有最多 ~一个 tick_interval 的延迟 → 选足够小的默认（如 5~15s），对分钟级及以上任务无感；不追求秒级精确。
- **[cron 下次计算]** 需可靠的 cron 下一次时间计算。优先复用现有 `_parse_cron`/croniter（Hermes 用 croniter；确认 fleetent 是否已有依赖，否则用现成解析）。→ 缓解：实现时统一走一个 `compute_next_run(kind, spec, base)` 纯函数，单测覆盖 cron/interval/once 与 DST/timezone。
- **[maintenance jobs 迁移]** `_register_maintenance_jobs`（spillover cleanup）依赖 APScheduler → 一并迁为 tick 引擎内的固定周期内部任务，避免遗留 APScheduler。
- **[历史无限增长]** → 保留上限 N + 删除任务级联清理（D5）。
- **[并发堆积]** LLM run 慢于产生速度 → 信号量上限 + 到期任务下次已推进，不会对同一任务并发（D2/D3 claim 保证同一任务同一时刻至多一次）。

## Migration Plan

1. 追加 `scheduled_task_runs` 迁移（forward-only，migrate-on-open）。
2. 引擎替换在 `cron_scheduler.py` 内完成，保持 facade/构造/start/shutdown 契约；首次 start 为缺 `next_run_at` 的既有任务回填。
3. 部署即生效（agent 重启加载新引擎）；旧 APScheduler 无持久状态，无数据迁移负担。
4. **回滚**：还原 `cron_scheduler.py`（与依赖）即可；`scheduled_task_runs` 表为附加表，回滚后闲置无害（forward-only 不回退 schema）。

## Open Questions

- cron 下一次时间：确认是否引入/已存在 croniter（自托管友好，纯库），还是用现有 5 字段解析自算下一次。实现阶段以"能否可靠算 DST 安全的下一次"为准，二选一并单测。
- tick_interval / 并发上限的默认值最终取值（建议 tick 10s、并发 4），实现时定并可配。
