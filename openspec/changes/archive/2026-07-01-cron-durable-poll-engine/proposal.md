## Why

定时任务在短周期 `generate`/`action` 任务上会**静默漏触发、间隔混乱**（Jira AAA-8209 症状②，已用 Slack 复现）。根因：现调度基于 APScheduler 内存触发器，`_fire` 内联 `await` 一整轮 LLM（10~60s+），当单次运行时长 ≳ interval 时，后续 tick 撞 `max_instances=1` 被判 missed、再被 `coalesce` 合并成一次 —— 该触发时刻被**悄悄丢弃**，且全程无记录、不可见。同时运行状态只覆盖单行 `last_*`，**没有逐次运行历史**，无法回答"触发了几次、每次结果如何"（症状③）。

参考现有生产系统 Hermes 的 cron 设计（持久 `next_run_at` + 轮询到期 + **执行前先推进** + 逐次输出落盘），其"调度节奏与单次运行时长解耦"正是本问题的正解。

## What Changes

- **BREAKING（内部实现）**：`cron_scheduler` 的调度引擎从 APScheduler 内存触发器替换为**持久化 `next_run_at` + 轻量 asyncio tick 轮询**引擎（fleetent 单进程，无需 Hermes 的跨进程文件锁；用进程内并发保护）。对外公共 API（`create_task`/`remove_task`/`set_task_enabled`/`run_task_now`/`list_tasks` + 模块 facade + `schedule` 工具）**签名与行为契约保持不变**，调用方（`agent_app`、`server.py`、工具层）无需改造。
- **执行前先推进 `next_run_at`**：到期任务在执行前、在并发保护内先把 `next_run_at` 推到下一周期（interval 从 `last_run + 间隔`；cron 从当前时刻算下一次），再运行 → **调度节奏与单次运行时长解耦**，根治静默漏触发；崩溃不重放（at-most-once）。
- **陈旧计划快进**：`next_run_at` 落后超过一个周期（宕机/重启）时快进到下一个未来时刻，不爆发式补发。
- **有界并行执行**替代强制串行：慢任务不阻塞其它任务与调度节拍，并发上限可配。
- **逐次运行历史（#3）**：agent_state.db 新增 `scheduled_task_runs` 表，每次触发记一行（时间/状态 ok|error|missed|skipped/agent 错误/投递错误分离/耗时/类型），并对每任务保留最近 N 行；`schedule` 工具新增 `history` 动作查询某任务最近运行。

## Capabilities

### New Capabilities
- `cron-run-history`: 定时任务逐次运行历史的持久化（`scheduled_task_runs` 表、agent 错误与投递错误分离、保留上限）与查询出口（`schedule` 工具 `history` 动作）。

### Modified Capabilities
- `cron-scheduled-tasks`: 触发引擎由「APScheduler 内存触发器 + misfire_grace_time/coalesce/max_instances」改为「持久 `next_run_at` + 轮询 + 执行前先推进 + 陈旧快进 + 有界并行」。受影响需求：`Cron trigger fires agent run asynchronously`（改为轮询+先推进、非阻塞、不静默丢触发）、`Schedule kinds cron/one-shot/interval`（去 APScheduler trigger 绑定，改为 `next_run_at` 计算语义）、`Missed-run handling on restart`（去 coalesce/misfire，改为陈旧快进+先推进的 at-most-once）、`Scheduler global settings`（去"start APScheduler"措辞，改为启动 tick 轮询；新增 tick 周期/并发上限可配）。

## Impact

- **代码**：`cron_scheduler.py`（引擎替换，公共 API 不变）、`schedule_store.py`（新增运行历史读写 + 任务 `next_run_at` 推进/查询）、`runtime/agent_state_migrations.py`（追加 `scheduled_task_runs` 表迁移，forward-only）、`tools/builtin_tools.py`（`schedule` 工具新增 `history` 动作）、`config.py` `SchedulingSettings`（tick 周期/并发上限/历史保留条数可注入项）。
- **接线**：`runtime/agent_app.py`（构造/启动不变，内部改为启动 tick）、`server.py`（`set_principal_resolver` 注入契约不变）。
- **依赖**：本模块内移除对 APScheduler 的使用；若无其它使用方则可从依赖清单移除（届时确认）。
- **模块边界**：`cron_scheduler`/`schedule_store` 仍严禁 `import fleetent.platform.*`、不触碰 platform 表（护栏 `test_module_dependency_guardrails` 保持绿）；运行历史落 agent_state.db（agent 侧）。
- **不在范围**：跨进程文件锁/独立 daemon、定时任务管理 UI、notify/generate/action 语义与投递契约、"第N次计数注入消息内容"（已判定不做）。
- **迁移**：agent_state.db 嵌入式 forward-only 迁移追加运行历史表；无 platform（Alembic）schema 变更。
