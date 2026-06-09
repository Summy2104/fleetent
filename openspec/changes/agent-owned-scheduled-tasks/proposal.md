## Why

定时任务当前是 **platform-owned**：`scheduled_tasks` 表由 Alembic 在 platform DB 建表，`CronScheduler` 只在 platform server 的 FastAPI lifespan 启动。这违反 agent/platform 解耦硬规则——agent 运行时的 `schedule_task` 工具反向写 platform 表，且 `fleetent agent run` 独立态既无表也无调度器（实测：黑盒 E2E 中 `schedule_task` 报「数据库表尚未初始化」，功能失效）。定时任务本质属于 agent 运行时、每个 agent 独有、不共享，应与 platform 完全无关。

此外当前 `_fire` 跑完 agent loop 只存 session、**不主动推送**，用户根本收不到提醒——「定时提醒」这一核心价值未真正实现。

## What Changes

- `schedule_store` 改为 agent 自持 schema（仿 `governance/approval_store`：模块自己 `ensure_schema`，去 Alembic 依赖），并加入 `agent_app._init_agent_db_schema` —— 修复独立态 `fleetent agent run` 缺表（BUG-2）。`scheduled_tasks` 加入 agent-side 双权威表，DDL 与 Alembic head 一致（漂移护栏强制）。
- `CronScheduler` 移入 agent 运行时（`agent_app.boot` 起、`stop` 关，注入连接器解析器），使任务在无 platform 时也能触发。
- **BREAKING**：合并 `schedule_task` + `cancel_task` 为单个 `schedule(action=create|list|remove|run_now|pause|resume)` 工具，`risk_level="low"`、不走审批。
- 调度类型从仅 cron 扩展为 **cron + one-shot（绝对时间/时长）+ interval**。
- 触发后**主动投递回复**：投递目标在**触发时**解析（显式 `deliver` 优先，否则回 `origin`）；回复为 `[SILENT]` 时只存档不打扰；连接器经进程级 `im_gateway/connector_registry`（适配器连接时注册）解析。
- 新增可观测列 `last_run_at` / `last_status` / `last_error` / `next_run_at`；漏跑用 APScheduler 原生 `misfire_grace_time` + `coalesce` + `max_instances`。
- **非破坏迁移**：Alembic `067` **加列**（schedule_kind/run_at/interval/origin/deliver/运行态），与 ensure_schema 对齐；**保留 `agent_name`（可空）** 与平台调度器/admin CLI —— 因平台 `agent_statistics.stats_admin_api` 仍用 `schedule_store`+`agent_name` 注册统计邮件报表（见下「Non-Goals」），「彻底移除平台侧」暂缓待该依赖处置后单独进行。

## Non-Goals / Deferred（本 PR 不做，原因见 design.md）

- **彻底移除平台侧调度（drop 表 / 去 server cron / 删 admin CLI）**：与平台 `stats_admin_api` 的统计邮件报表依赖冲突（多 agent、平台触发、需 agent_name），需先决定 stats 报表去向，留作后续。
- **媒体附件投递**：`outbound` 仅发文本；复用 IM 上传路径留 v2。
- **origin 自动捕获**：需把 IM 上下文透传进 `ToolContext`；当前工具支持显式 `notify_*` 目标，origin 解析逻辑已就位待自动填充。

## Capabilities

### New Capabilities
- `scheduled-task-delivery`: 定时任务触发后将 agent 输出主动投递给用户/频道——触发时解析目标、默认回 `origin`、可显式覆盖渠道与目标、`[SILENT]` 抑制、连接器不可用时优雅跳过并记 `last_error`。

### Modified Capabilities
- `cron-scheduled-tasks`: 归属从 platform 改为 agent 运行时（自持 schema + 调度器进 agent 进程）；工具合并为单个 `schedule(action=...)` 且 `risk_level=low` 不审批；调度类型扩展为 cron/one-shot/interval；新增运行态可观测列。`schedule_task`/`cancel_task` 工具移除（折叠进 `schedule`）。

## Impact

- 代码：`schedule_store.py`、`cron_scheduler.py`、`runtime/agent_app.py`、`tools/builtin_tools.py`（工具合并）、`outbound.py`（频道/线程投递）、`im_gateway/{slack,telegram}.py`（连接器注册）、新增 `im_gateway/connector_registry.py`。
- 数据：Alembic `067` **加列**（非 drop），与 ensure_schema 对齐；agent 侧 `fleetent.db` 经 ensure_schema 自建 `scheduled_tasks`。不迁移既有平台行。
- 依赖：沿用 APScheduler；无新增第三方依赖。
- 解耦：`schedule_store`/`cron_scheduler` MUST NOT import `fleetent.platform.*`；验证基线为无平台、平台表不存在时 `fleetent agent run` 可创建并触发定时任务。
- 不变：`scheduled-task-session-binding`（session_id 绑定语义保持）。
