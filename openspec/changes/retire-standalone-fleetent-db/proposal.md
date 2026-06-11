## Why

standalone agent（`fleetent agent run`）的 `DATABASE_URL` 仍指向 `data/fleetent.db`——这是**改名前管理库的同名**，与已落地的 `management.db` 并存，语义不明、易混淆（"这个 `fleetent.db` 是没改名的旧管理库还是别的？"）。

更深的根因：`scheduled_tasks` 已由 alembic 071 从管理库 drop、判为 **agent 侧 per-agent 表**，但它**没有并入 `agent_state.db` 的统一嵌入式迁移（AGENT_STATE_MIGRATIONS）**，而是经遗留的 `schedule_store.ensure_schema()` 单独建在 `DATABASE_URL` 库里。结果：

- `scheduled_tasks` 成了游离表——所有其它 agent 侧表（sessions/traces/reflection/memory/approvals/budget/...）都住在 `agent_state.db`、由嵌入式 Y 建，唯独它落在 `fleetent.db`。
- `schedule_store.ensure_schema()` 是**最后一个残留的 store 侧 `ensure_schema`**（其余已由 `retire-ensure-schema-drift-guardrail` 收口到嵌入式 Y），违反"agent 侧表统一走 `MIGRATIONS` + `PRAGMA user_version`"约定。
- `fleetent.db` 因此仅为承载这一张表（+ 充当 data_dir 锚点）而存在。

scheduler 定位已查清：用户 scheduled_tasks 是 **agent-owned**，由每个 agent 进程的 `CronScheduler` 触发；平台 managed 侧只跑自己的维护 scheduler（playground 清理），完全不碰 scheduled_tasks。所以 scheduled_tasks 100% 属 agent 侧 per-agent，理应与其它 agent 侧表同住 `agent_state.db`。

把 scheduled_tasks 折进 `agent_state.db` 后，`fleetent.db` 再无内容，可彻底退役——命名混淆消失，agent 侧 schema 权威完全统一到嵌入式 Y。

## What Changes

- `scheduled_tasks` 表定义并入 `runtime/agent_state_migrations.py` 的统一 `AGENT_STATE_MIGRATIONS`（新增一版），DDL 从 `schedule_store` 原样 lift（保留全部列、named parameters、`agent_name` 列不存在）。
- `schedule_store` 改为**注入式**：新增 `set_state_db(db)`（与 `traces`/`reflection`/`memory_store` 等同款），CRUD 走注入的 `agent_state.db`；删除 `ensure_schema()` 与 `_database()` 的 `Settings().database_url` 自连接。
- `agent_app`：`_init_agent_db_schema` 不再吃 `database_url`、改吃 `data_dir`（router 直接锚 `home_dir/data`），并 `schedule_store.set_state_db(agent_state_db)`；`_redirect_agent_data_paths` 不再设 `DATABASE_URL=fleetent.db`；`_start_infra` 的 schema 初始化触发从"`DATABASE_URL` 是否设"改为"data_dir 存在即初始化"。
- 退役 `fleetent.db`：standalone 不再创建该文件。
- 顺手清死代码：`db.py` 的 `default_database()`（零调用方的 backward-compat fallback，且是"未注入 → 落 `management.db`"的潜在地雷）移除。
- 文档：`data-model.md` 把 `scheduled_tasks` 从 §3.2 管理库移到 §3.3 per-agent；修 `runtime/context.py:665` 过时注释（"per-agent `fleetent.db`" → `agent_state.db`）。

数据迁移：按项目"上线前不迁移数据"约定，`scheduled_tasks` 在 `agent_state.db` 全新建立，旧 `fleetent.db` 作孤儿由部署方按需清理（pilot 前无真实持久 cron 数据）。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `cron-scheduled-tasks`: `scheduled_tasks` 的 schema 权威与库归属从"`schedule_store.ensure_schema()` + `DATABASE_URL` 库"改为"`agent_state.db` 的嵌入式 Y + 注入式 `set_state_db`"。
- `agent-db-schema-self-init`: standalone boot 的 agent 侧 schema 初始化不再以 `DATABASE_URL`/`fleetent.db` 为锚，改以 per-agent `data_dir` 驱动；`scheduled_tasks` 纳入 boot 时统一建表集合。

> `agent_state.db` 的 `MIGRATIONS` 新增一版承载 `scheduled_tasks` 属嵌入式 Y 引擎的既有机制（`embedded-schema-migration` 引擎不变，无 spec 级变更）；`db.default_database()` 移除、`context.py` 注释、`data-model.md` 同步均为实现/文档层（见 tasks），不产生 spec delta。

## Impact

- **owning package**：`runtime`（`agent_state_migrations` / `agent_app`）+ 顶层 agent 侧模块 `schedule_store`
- **public API surface**：`schedule_store.set_state_db(db)` 新增；`schedule_store.ensure_schema` 移除；`db.default_database()` 移除
- **owned tables**：`scheduled_tasks` 从 standalone `fleetent.db` → per-agent `agent_state.db`（嵌入式 Y 新增一版）
- **config namespace**：无新增
- **cross-module dependencies**：`agent_app` 注入 `schedule_store`（与现有 traces/reflection/memory 注入同模式）；`cron_scheduler` 经 `schedule_store` 公开 API 消费，无需改动其依赖方向
- **migration / shim plan**：agent 侧表新建（forward-only）；旧 `fleetent.db` 不迁移、作孤儿；`schedule_store` 无对外路径常量需保留 shim（`ensure_schema` 仅被 `agent_app` 内部调用，一并改）
- **affected code**：`runtime/agent_state_migrations.py`、`schedule_store.py`、`runtime/agent_app.py`、`runtime/context.py`（注释）、`db.py`（删 `default_database`）、`docs/architecture/data-model.md`
- **解耦验证基线**：改动后 agent 仍须能在「无 platform、管理库不存在」环境完成 `fleetent agent run`（本 change 反而消除了 standalone 误指 `management.db` 的隐患）
