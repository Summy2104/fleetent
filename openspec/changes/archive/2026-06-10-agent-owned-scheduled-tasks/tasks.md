## 1. schedule_store 改 agent 自持 schema

- [x] 1.1 Tests: `schedule_store.ensure_schema` 自建表；CRUD 含新列（schedule_kind/run_at/interval_seconds/anchor/origin/deliver/运行态）；named params；drift 护栏纳入 scheduled_tasks
- [x] 1.2 重写 `schedule_store`：模块 `ensure_schema`（仿 approval_store），扩展 create/list/get/set_enabled/update_run_state/delete；origin/deliver JSON 编解码
- [x] 1.3 加入 `agent_app._init_agent_db_schema`
- [x] 1.4 解耦：`schedule_store`/`cron_scheduler` 无 `import fleetent.platform.*`（保留对 `config.Settings` 的 DB-url 解析，非平台依赖）
- [x] 1.5 `scheduled_tasks` 成纯 agent-side 表（仅 ensure_schema 自建，无 `agent_name`）；Alembic `067` drop 平台表（见 §7.2）

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
- [x] 5.4 origin 自动捕获：`schedule` create 从 `tool_context.session_context` 自动构建 `origin`（platform / chat_id=channel_name / thread_id=thread_root, target_type=channel），默认投递回创建会话/线程；显式 `notify_*` 仍优先，无 IM 上下文时 origin=None

## 6. 工具合并为单个 schedule(action=...)

- [x] 6.1 Tests: create/list/remove/run_now/pause/resume；`risk_level=low` 不审批；旧两工具已移除
- [x] 6.2 `schedule` 工具实现；删除 `schedule_task`/`cancel_task`

## 7. 平台侧彻底移除（DONE）

- [x] 7.1 删桩：平台 `stats_admin_api` 的 `POST /admin/stats/reports` + `schedule_report`/`ReportBody` 移除（该桩只登记任务+审计，从无邮件实现：无 `__stats_report__` 处理器、无 SMTP）；更新 stats 测试
- [x] 7.2 Alembic `067` drop 平台 `scheduled_tasks` 表（downgrade 重建 002+042 schema）；`scheduled_tasks` 成纯 agent-side 表（漂移护栏跳过无 Alembic 对应的表）
- [x] 7.3 `server.py` 用裸 `AsyncIOScheduler` 替换 `CronScheduler`，仅跑平台维护（playground 保留），不再加载/触发用户定时任务；删死代码 `_run_monitoring_cycle`
- [x] 7.4 admin CLI 删除 `list/add/remove-schedule`（删 `schedules.py` + main.py 注销）
- [x] 7.5 删 `agent_name` 列（一进程一 agent，隐含）；store/DDL/create + 相关测试同步

## 8. 收尾

- [x] 8.1 解耦验证：drift 护栏（alembic head vs ensure_schema）覆盖 scheduled_tasks，绿
- [x] 8.2 改动文件 ruff format/lint、mypy
- [x] 8.3 `make test-pr` 绿 + `tests/integration` 对照 main 基线无新增失败
