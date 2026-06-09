## Context

定时任务现为 platform-owned：`scheduled_tasks` 表由 Alembic 在 platform DB 建表，`CronScheduler` 仅在 platform server lifespan（`server.py`）启动，并从 Platform settings 读调度配置。agent 运行时的 `schedule_task` 工具反向写 platform 表，违反 agent/platform 解耦硬规则；`fleetent agent run` 独立态既无表也无调度器，功能静默失效。

刚合并的 `governance/approval_store.py` 提供了「agent 自持 store」的标准范式（模块 `ensure_schema` + `paths.data_dir()/fleetent.db` + 零 platform import，在 `agent_app._init_agent_db_schema` 建表）；`outbound.send_to` 提供了零 platform 依赖的主动外发原语；`im-generated-image-upload` 能力下，正常 IM 回复路径已能上传 generate_image 产物。本设计在这些既有件上完成迁移。

参考实现：`NousResearch/hermes-agent` 的 `cron/`（文件 JSON、`deliver:origin`、`[SILENT]`、grace window）与 `openclaw/src/cron/`（croner、触发时解析投递目标、staggered 启动恢复、运行态 sidecar）。两者趋同的核心经验已收敛进下列决策。

## Goals / Non-Goals

**Goals:**
- 定时任务完全归 agent 运行时，每 agent 独有、不共享、与 platform 无关；无平台、平台表不存在时 `fleetent agent run` 可创建并触发。
- 触发后主动把 agent 输出投递给用户/频道，默认回到创建上下文。
- 支持 cron / one-shot / interval 三类调度。
- 进程重启后不补跑风暴、不重复触发。

**Non-Goals:**
- 失败专用告警通道 + 冷却（监控语义，已外置；留 v2）。
- per-task skills / context_from（与 read-on-demand 重复 / 需输出存储；v2）。
- 迁移既有平台 `scheduled_tasks` 行（早期阶段无生产数据）。
- 改动 `scheduled-task-session-binding` 的 session_id 绑定语义（保持不变）。

## Decisions

**D1 — store 改 agent 自持，仿 `approval_store`。** `schedule_store` 去掉 `Settings().database_url`，改 `DB_PATH = paths.data_dir()/fleetent.db` + 模块 `ensure_schema`（`CREATE TABLE IF NOT EXISTS`，named params，`db_path` 可注入），并加入 `agent_app._init_agent_db_schema`。*为何*：与刚合并的审批迁移同构，最小认知成本，满足解耦。*备选*：继续依赖 Alembic——被否，平台耦合且独立态缺表。

**D2 — 调度器进 agent 进程。** `CronScheduler` 在 `agent_app.boot` 于 IM supervisors 起好后启动，注入一个连接器解析器 `() -> {"slack": <client>, "telegram": <bot>}`（仿 `permission_gate` 的 `outbound_connectors` dict）。调度配置取自 `agent.yaml`（`agent.scheduling`，已存在）。*为何*：平台部署中每个 agent 也是独立进程（`fleetent agent run`，见 platform-agent-lifecycle），单点放置即覆盖独立态与平台态。*备选*：平台 server 起调度——被否，违反「与 platform 无关」。

**D3 — 平台侧彻底移除。** Alembic 新增 drop migration 删 `scheduled_tasks`（仿 063/064）；`server.py` lifespan 去掉 `CronScheduler` import/start/shutdown；移除 admin CLI 的 `list/add/remove-schedule` 与 Platform settings 调度字段读取。*为何*：去耦 + 清死代码。

**D4 — 投递目标在触发时解析，默认 origin。** 任务存 `origin`（创建上下文：platform/chat_id/thread_id）与可选显式 `deliver`（mode=origin|explicit|none，platform/target/target_type/thread）。fire 时按 `deliver` 解析活连接器与目标再投递。*为何*（借鉴 hermes/openclaw）：连接器可能晚于任务注册才就绪、重连后地址不变；触发时解析比创建时绑定更稳，并天然实现「提醒我这里」。*备选*：创建时固定连接器引用——被否，重启后失效。

**D5 — 调度类型用 APScheduler 原生 trigger。** cron→`CronTrigger.from_crontab`，one-shot→`DateTrigger`，interval→`IntervalTrigger`。任务存 `schedule_kind` + 对应字段（`cron_expr` / `run_at` / `interval_seconds`+`anchor`）。*为何*：覆盖「30 分钟后」「每 90 分钟」等 cron 表达不了的诉求，且复用已引入的 APScheduler。

**D6 — 漏跑用 APScheduler 原生能力。** 注册 job 时设 `misfire_grace_time`（按周期推导）、`coalesce=True`、`max_instances`（并发上限）；boot 时按当前时间重算 `next_run_at`。*为何*（对比 hermes/openclaw 手写 grace window）：原生机制覆盖补跑收敛 / 防重触发 / 并发控制，代码更少。one-shot 过期超 grace 即标记 `completed` 不再跑。

**D7 — 媒体投递复用现有 IM 回复上传路径。** fire 的回复经与正常 IM 回复同一渲染/上传通道送出（`im-generated-image-upload` 已上传 generate_image 产物，实测验证），而非给 `outbound.send_to` 另造文件上传。需把「带附件的 IM 外发」抽为可被 fire 复用的函数。*为何*：避免重复逻辑、与正常回复行为一致。

**D8 — `[SILENT]` 抑制。** fire 跑出的最终回复文本恰为 `[SILENT]` 时，记 `last_status=ok` 但不投递。*为何*（借鉴 hermes）：支持「有变化才提醒」类任务，低成本。

**D9 — 工具合并为单个 `schedule`。** `schedule(action=create|list|remove|run_now|pause|resume, ...)`，`risk_level="low"`、不走审批；`pause/resume` 即 `enabled` 开关 + 注册/摘除 job。*为何*（借鉴 hermes/openclaw 单工具多 action）：比 `schedule_task`+`cancel_task` 更顺手、易扩展；low risk 按产品决策。删 `agent_name` 列（一进程一 agent）。

## Risks / Trade-offs

- [调度器仅在 agent 进程存活时触发，进程长时间宕机会漏跑] → D6 的 `misfire_grace_time` + boot 重算 `next_run_at`；one-shot 过期作废而非堆积。
- [媒体投递复用 IM 上传路径会与回复渲染耦合] → 把「带附件外发」抽成独立函数，fire 与正常回复共用同一入口，避免在两处各写一份。
- [origin 描述符可能失效（频道删除/用户退群）] → 投递 best-effort，失败写 `last_error`/`last_status`，不崩 fire。
- [interval 锚定语义（从创建锚定）与 cron 对齐语义不同，易混淆] → 工具 docstring 明确说明，create 时回显下次触发时间。
- [drop 平台表为破坏性操作] → 早期无生产数据；迁移顺序为先上 agent 侧再删平台表，留无重叠窗口；回滚靠 revert（表可由 agent 侧重建，平台表本就将废弃）。

## Migration Plan

1. 新增 agent 侧：`schedule_store` 自持 schema + 加入 `_init_agent_db_schema`；`agent_app.boot` 起 `CronScheduler` + 连接器解析器。
2. fire 改造：origin/deliver 解析 + 复用 IM 上传路径 + `[SILENT]` + 运行态列回写。
3. 工具合并为 `schedule(action=...)`（low risk）。
4. 调度类型扩展（cron/once/interval）+ 漏跑参数。
5. 平台移除：Alembic drop migration 删表；`server.py` 去 cron；admin CLI 去调度命令；移除 Platform settings 调度字段。
6. 回滚：revert 该 change；agent 侧表幂等可重建，平台表已计划废弃，无数据迁移负担。

## Open Questions

- 平台态下确认每个 agent 均以独立进程运行（`fleetent agent run`），从而 D2 单点放置充分——按 platform-agent-lifecycle 现状假定成立；若平台存在 in-process 多 agent 运行路径，需在该路径另起 per-agent 调度器（当前不认为存在）。
