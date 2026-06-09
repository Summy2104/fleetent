## 1. schedule_store 改 agent 自持 schema

- [ ] 1.1 Write failing tests: `schedule_store.ensure_schema()` 在全新 agent DB（未跑 Alembic）建表；CRUD 含新列（`schedule_kind`/`run_at`/`interval_seconds`/`origin`/`deliver`/`last_run_at`/`last_status`/`last_error`/`next_run_at`），无 `agent_name` 列；named params；`db_path` 可注入（tmp_path）
- [ ] 1.2 重写 `schedule_store`：去掉 `Settings().database_url`，改 `DB_PATH = paths.data_dir()/fleetent.db` + 模块 `ensure_schema`（仿 `governance/approval_store`），扩展 `create`/`list_tasks`/`delete` 支持新列与 `schedule_kind`；运行态列读写辅助函数
- [ ] 1.3 把 `schedule_store.ensure_schema` 加入 `agent_app._init_agent_db_schema`；测试 boot 后表存在
- [ ] 1.4 确认 `schedule_store`/`cron_scheduler` 无 `import fleetent.platform.*`（解耦断言测试）

## 2. 调度类型 cron / one-shot / interval

- [ ] 2.1 Write failing tests: cron→`CronTrigger.from_crontab`、once→`DateTrigger`(绝对/相对时长)、interval→`IntervalTrigger`(锚定创建) 三类注册触发；one-shot 触发后置 `completed`
- [ ] 2.2 在 `cron_scheduler._register` 按 `schedule_kind` 选 APScheduler trigger；实现相对时长解析（如 `+30m`）→ `run_at`

## 3. 漏跑处理

- [ ] 3.1 Write failing tests: 注册 job 带 `misfire_grace_time`+`coalesce=True`+`max_instances`；重启后 recurring 合并补跑为一次；过期超 grace 的 once 置 `completed` 不触发
- [ ] 3.2 在 `_register`/boot 重算 `next_run_at` 并应用上述 APScheduler 参数；过期 once 的收敛逻辑

## 4. 调度器进 agent 进程

- [ ] 4.1 Write failing tests: `agent_app.boot` 在 IM supervisors 起好后启动 `CronScheduler`，注入连接器解析器 `()->{"slack":client,"telegram":bot}`；`agent.scheduling.enabled=false` 时不启动；默认时区取 `agent.scheduling.default_timezone`
- [ ] 4.2 在 `agent_app.boot`/`_start_infra` 启动调度器并注入连接器解析器；调度配置取自 `agent.yaml`

## 5. fire 改造 + 投递（scheduled-task-delivery）

- [ ] 5.1 Write failing tests: fire 跑 `agent_loop.run` 后据 `deliver`/`origin` 解析目标，调用复用的「带附件 IM 外发」函数投递回复（mock connector，断言 target/platform/thread 正确）；`origin` 默认回创建上下文；显式 `deliver` 覆盖（channel vs user、跨平台）；连接器不可用→记 `last_error` 不崩；`[SILENT]`→不投递且 `last_status=ok`
- [ ] 5.2 把「带附件的 IM 回复外发」从正常回复路径抽为可复用函数（复用 `im-generated-image-upload` 上传逻辑），供 fire 与正常回复共用
- [ ] 5.3 改造 `cron_scheduler._fire`：保留 `session_id` 绑定语义；run 后解析 deliver/origin → 投递；写回 `last_run_at`/`last_status`/`last_error`；`[SILENT]` 抑制
- [ ] 5.4 创建任务时捕获 `origin`（platform/chat_id/thread_id）写入任务（IM 上下文经 ToolContext 透传）

## 6. 工具合并为单个 schedule(action=...)

- [ ] 6.1 Write failing tests: `schedule(action="create"|"list"|"remove"|"run_now"|"pause"|"resume")` 各分支；`risk_level="low"` 且不触发审批；create 回 id；pause/resume 切 `enabled` 并注册/摘除 job；run_now 立即触发；remove 不存在 id 返回错误串不抛
- [ ] 6.2 在 `tools/builtin_tools.py` 实现 `schedule` 工具（low risk），删除 `schedule_task`/`cancel_task`；create 默认 deliver=origin、可显式覆盖 platform/target/target_type/thread

## 7. 平台侧彻底移除

- [ ] 7.1 Write failing tests: Alembic 新增 drop migration 后 `scheduled_tasks` 表在平台 DB 不存在（仿 `test_askit_tables_dropped`/`test_monitoring_migration`）；`server.py` lifespan 不再启动 CronScheduler；admin CLI 无 `list/add/remove-schedule`
- [ ] 7.2 新增 Alembic drop migration 删平台 `scheduled_tasks` 表（仿 063/064）
- [ ] 7.3 `server.py` lifespan 移除 `CronScheduler` import/start/shutdown
- [ ] 7.4 移除 admin CLI 的 `list/add/remove-schedule` 命令与 Platform settings 调度字段读取

## 8. 收尾

- [ ] 8.1 端到端解耦验证：无平台、平台表不存在时 `fleetent agent run` 可 `schedule(action="create")` 并按时触发、投递回 origin
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests`、`uv run mypy src`
- [ ] 8.3 `uv run python scripts/check_test_layers.py`、`uv run pytest -x -q` 全绿
