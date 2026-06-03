## Why

定时任务（cron）每次触发都会构造一条 `user` 消息并调用 `agent_loop.run()`（`cron_scheduler._fire` 行 25-28），但**当前实现完全不绑定 session**：`_fire` 既不传 `session_id`，也不在触发前后 load/save 任何 session 文件。结果是每次触发都是「无记忆」的孤立运行——没有跨触发的上下文累积，也没有「复用同一对话」的能力。

`scheduling.md` 待决问题中「`session_id` 绑定语义」与 `session.md` 规划项「定时任务 session 绑定语义」均已给出方向（见 session.md 第 83-88 行、scheduling.md 第 449 行）：

- `session_id` **指定**时：复用该 session 的完整历史上下文（适合持续性任务，如每日报告需要记住上次说了什么）。
- `session_id` **未指定**时：每次新建独立 session，上下文不跨触发保留（适合无状态定时操作，如「每小时拉一次监控数据并播报」）。
- 两种语义在任务配置中**显式声明，不做隐式推断**。

本 change 落地这一语义决策：为 `scheduled_tasks` 增加可选 `session_id` 字段，并把 `_fire` 接到 `session_mgr.load` / `session_mgr.save` 与 per-session `asyncio.Lock` 上。这是 scheduling × session 的跨域 change，build on 已实现的 `cron_scheduler` / `schedule_store` / `session_mgr`。

## What Changes

- **绑定语义决策（结论）**：定时任务每次触发的 session 绑定为**可配置**——
  - 任务声明了 `session_id`：每次触发**复用同一固定 session**，跨触发累积上下文（持续性语义）。
  - 任务未声明 `session_id`（默认）：每次触发**新建一个独立、互不可见的 session**，上下文不跨触发保留（无状态语义，与现状的「无记忆」行为最接近，是安全默认）。
  - 不引入「按某 key 自动派生 session」之类的隐式推断；只有「显式固定」与「每次独立」两态。
- `scheduled_tasks` 表**增加可选列 `session_id TEXT`**（NULL = 每次独立）；`schedule_store.create` / `list_tasks` / `load_cron_yaml` 承载该字段。
- `cron_scheduler._fire`：
  - 解析任务的 `session_id`：为 None 时**派生一个每次触发唯一的独立 session_id**（如 `cron/{task_id}/{run_uuid}`，保证互不可见）；非 None 时使用任务指定的固定 session_id。
  - 触发前在 per-session `asyncio.Lock` 下 `session_mgr.load(sid)` 取历史，拼接本次 `user` 消息后调用 `agent_loop.run()`，完成后 `session_mgr.save(sid, updated, user_id=..., agent_name=...)`。
- session_id 取值遵循 `session.md` 约定的定时任务格式：固定语义用调用方指定值（或 `cron/{task_id}`），独立语义用 `cron/{task_id}/{run_uuid}`。

## Capabilities

### New Capabilities
- `scheduled-task-session-binding`: 定时任务触发时的 session 绑定语义可配置——声明 `session_id` 则跨触发复用固定 session 累积上下文，未声明则每次触发新建独立 session（默认、无状态），语义显式声明不隐式推断，并据此接 `session_mgr` load/save 与 per-session 锁。

### Modified Capabilities
<!-- 不以 MODIFIED 表达既有 spec。`cron-scheduled-tasks`（_fire 触发 agent run）与 `session-persistence`（load/save）的既有需求均不变；本 change 在其之上新增「触发时如何绑定 session」这一新维度，落在新 capability `scheduled-task-session-binding` 下以 ADDED 表达，避免 archive sync 找不到同名既有需求。 -->

### 共享资源引用
- **`scheduled_tasks` 表 owner = cron-scheduled-tasks（已归档）**：本 change 仅向该表**追加**可选列 `session_id`，不改既有列语义，新列默认 NULL 与现状等价。
- **`data/sessions/{session_id}.json` + per-session 锁 owner = session-persistence（已归档）**：本 change 仅作为新调用方接入既有 `load` / `save` / `session_lock`，不改其行为。

## Impact

- **代码**：
  - `src/fleetent/schedule_store.py`：`scheduled_tasks` 建表语句增列 `session_id TEXT`；`create` 增可选参数 `session_id: str | None = None` 并写入；`list_tasks` 返回该字段（`SELECT *` 已覆盖，dict 自动带出）。
  - `src/fleetent/cron_scheduler.py`：`load_cron_yaml` 解析 `session_id`；`_fire` 据 `session_id` 决定固定/独立 session，接 `session_mgr.load`/`save` 与 `session_lock`。
- **数据**：`scheduled_tasks` 表新增列（向后兼容，旧库需 `db-migration` 走 `ADD COLUMN`；新列可空，缺省 NULL）。
- **测试**：扩充 `tests/test_schedule_store.py`（`session_id` 持久化与默认 NULL）、`tests/test_cron_scheduler.py`（固定语义跨触发复用、独立语义每次新 session、load/save 接线、锁串行）。`agent_loop.run` 与 `session_mgr` 路径全 mock / 隔离到 tmp_path，不发真实 LLM 调用。
- **不影响**：webhook 触发链路、APScheduler 注册逻辑、context_mgr、session TTL/容量清理（独立 session 由既有 `maybe_run_maintenance` 自然回收）。
- **不引入新依赖**：`uuid` / `asyncio` 均为标准库且已在用。

## Dependencies

- `src/fleetent/cron_scheduler.py`（已实现）：APScheduler 触发链路与 `_fire`，本 change 在 `_fire` 内接 session。
- `src/fleetent/schedule_store.py`（已实现，标准库 sqlite3）：`scheduled_tasks` 表定义与 CRUD，本 change 增列并承载 `session_id`。
- `src/fleetent/session_mgr.py`（已实现）：`load` / `save` / `session_lock`（per-session asyncio.Lock）、原子写，本 change 作为新调用方接入。
- 已归档 spec：`cron-scheduled-tasks`、`session-persistence`、`session-metadata-index`（save 时传 `user_id`/`agent_name` 顺带刷新元数据索引）。
