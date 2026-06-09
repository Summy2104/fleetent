## 1. schedule_store 改 agent 自持 schema

- [x] 1.1 Tests: `schedule_store.ensure_schema` 自建表；CRUD 含新列（schedule_kind/run_at/interval_seconds/anchor/origin/deliver/运行态）；named params；drift 护栏纳入 scheduled_tasks
- [x] 1.2 重写 `schedule_store`：模块 `ensure_schema`（仿 approval_store），扩展 create/list/get/set_enabled/update_run_state/delete；origin/deliver JSON 编解码
- [x] 1.3 加入 `agent_app._init_agent_db_schema`
- [x] 1.4 解耦：`schedule_store`/`cron_scheduler` 无 `import fleetent.platform.*`（保留对 `config.Settings` 的 DB-url 解析，非平台依赖）
- [x] 1.5 Alembic `067` 加列（非 drop），与 ensure_schema DDL 对齐；保留 `agent_name`（平台 stats 兼容）

## 2. 调度类型 cron / one-shot / interval

- [x] 2.1 Tests: once→DateTrigger、interval→IntervalTrigger、cron→CronTrigger；`_parse_run_at` ISO/相对时长
- [x] 2.2 `_register` 按 `schedule_kind` 选 trigger；`_parse_run_at` 实现

## 3. 漏跑处理

- [x] 3.1 Tests: job 带 `misfire_grace_time`+`coalesce`+`max_instances`
- [x] 3.2 `_register` 应用上述 APScheduler 参数

## 4. 调度器进 agent 进程

- [x] 4.1 Tests: `_start_scheduler` enabled→起调度器+连接器解析器；disabled→None；连接器解析读 `connector_registry`
- [x] 4.2 `agent_app.boot` 起调度器、`AgentRuntime.stop` 关；连接器解析器接 `connector_registry`

## 5. fire 改造 + 投递（scheduled-task-delivery）

- [x] 5.1 Tests: 投递回 origin / 显式 channel / `[SILENT]` 抑制 / 无连接器记 error
- [x] 5.2 `_fire` 捕获回复、解析 deliver/origin、`outbound.send_to` 投递、运行态写回；`outbound` 加频道/线程
- [x] 5.3 `connector_registry` + slack/telegram 适配器连接时注册、断开注销
- [ ] 5.4 （DEFERRED v2）origin 自动捕获：把 IM 上下文（platform/chat/thread）透传进 `ToolContext`，create 时自动填 `origin`。当前支持显式 `notify_*`，解析逻辑已就位

## 6. 工具合并为单个 schedule(action=...)

- [x] 6.1 Tests: create/list/remove/run_now/pause/resume；`risk_level=low` 不审批；旧两工具已移除
- [x] 6.2 `schedule` 工具实现；删除 `schedule_task`/`cancel_task`

## 7. 平台侧（DEFERRED — 见 design.md / proposal Non-Goals）

- [ ] 7.1 （DEFERRED）drop 平台 `scheduled_tasks` 表
- [ ] 7.2 （DEFERRED）`server.py` 去 CronScheduler
- [ ] 7.3 （DEFERRED）admin CLI 去调度命令
> 阻塞原因：平台 `agent_statistics.stats_admin_api` 用 `schedule_store`+`agent_name` 注册统计邮件报表（多 agent、平台触发）。彻底移除会破坏该功能，需先决定 stats 报表去向（迁为 agent 任务 / 平台保留自有调度）。本 PR 以非破坏 additive 迁移落地 agent 侧，平台侧维持现状。

## 8. 收尾

- [x] 8.1 解耦验证：drift 护栏（alembic head vs ensure_schema）覆盖 scheduled_tasks，绿
- [x] 8.2 改动文件 ruff format/lint、mypy
- [x] 8.3 `make test-pr` 绿 + `tests/integration` 对照 main 基线无新增失败
