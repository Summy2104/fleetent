## Why

定时任务当前是 **platform-owned**：`scheduled_tasks` 表由 Alembic 在 platform DB 建表，`CronScheduler` 只在 platform server 的 FastAPI lifespan 启动。这违反 agent/platform 解耦硬规则——agent 运行时的 `schedule_task` 工具反向写 platform 表，且 `fleetent agent run` 独立态既无表也无调度器（实测：黑盒 E2E 中 `schedule_task` 报「数据库表尚未初始化」，功能失效）。定时任务本质属于 agent 运行时、每个 agent 独有、不共享，应与 platform 完全无关。

此外当前 `_fire` 跑完 agent loop 只存 session、**不主动推送**，用户根本收不到提醒——「定时提醒」这一核心价值未真正实现。

## What Changes

- **BREAKING**：`schedule_store` 改为 agent 自持 schema（仿 `governance/approval_store`：模块自己 `ensure_schema`，库为 `paths.data_dir()/fleetent.db`，去掉 `Settings().database_url` 与 Alembic 依赖），并加入 `agent_app._init_agent_db_schema`。
- **BREAKING**：`CronScheduler` 移入 agent 运行时（`agent_app.boot` 启动并注入连接器解析器）；**平台侧彻底移除**——Alembic 新增 drop migration 删 `scheduled_tasks` 表，`server.py` lifespan 去掉 `CronScheduler`，移除 admin CLI 的 `list/add/remove-schedule` 命令与「从 Platform settings 读调度配置」。
- **BREAKING**：合并 `schedule_task` + `cancel_task` 为单个 `schedule(action=create|list|remove|run_now|pause|resume)` 工具，`risk_level="low"`、不走审批。
- 调度类型从仅 cron 扩展为 **cron + one-shot（绝对时间/时长）+ interval**。
- 触发后**主动投递回复**：投递目标在**触发时**解析，默认 `origin`（创建任务时的 platform/chat/thread 上下文），可对话覆盖为显式平台/目标/线程；回复为 `[SILENT]` 时只存档不打扰；媒体附件**复用现有 IM 回复上传路径**（如 generate_image 产物）。
- 新增可观测列 `last_run_at` / `last_status` / `last_error` / `next_run_at`；漏跑用 APScheduler 原生 `misfire_grace_time` + `coalesce` + `max_instances`。
- `scheduled_tasks` 删除 `agent_name` 列（一进程一 agent，隐含）。

## Capabilities

### New Capabilities
- `scheduled-task-delivery`: 定时任务触发后将 agent 输出主动投递给用户/频道——触发时解析目标、默认回创建上下文（origin）、可显式覆盖渠道与目标、`[SILENT]` 抑制、媒体附件复用 IM 上传路径、连接器不可用时优雅跳过。

### Modified Capabilities
- `cron-scheduled-tasks`: 归属从 platform 改为 agent 运行时（自持 schema + 调度器进 agent 进程 + 平台移除）；工具合并为单个 `schedule(action=...)` 且 `risk_level=low` 不审批；调度类型扩展为 cron/one-shot/interval；新增运行态可观测列；删除 admin CLI 调度命令与 Platform settings 调度配置；删 `agent_name` 列。

## Impact

- 代码：`schedule_store.py`、`cron_scheduler.py`、`runtime/agent_app.py`、`tools/builtin_tools.py`（工具合并）、`server.py`（移除 cron）、`platform/admin_cli`（移除调度命令）、`outbound.py` / IM 回复上传路径（媒体投递复用）。
- 数据：Alembic 新增 drop migration 删 platform `scheduled_tasks` 表（仿 063/064）；agent 侧 `fleetent.db` 新增 `scheduled_tasks`（模块自持 schema）。不迁移既有平台行（早期阶段无生产数据）。
- 依赖：沿用 APScheduler；无新增第三方依赖。
- 解耦：`schedule_store`/`cron_scheduler` MUST NOT import `fleetent.platform.*`；验证基线为无平台、平台表不存在时 `fleetent agent run` 可创建并触发定时任务。
- 不变：`scheduled-task-session-binding`（session_id 绑定语义保持）。
