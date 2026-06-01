## Context

`cron_scheduler._fire`（cron_scheduler.py 行 25-28）当前每次触发只做两件事：构造 `[{"role": "user", "content": task["message"]}]`，调用 `agent_loop.run(messages, user_id=..., agent_name=...)`。**它从不接触 session_mgr**——既不 load 历史，也不 save 结果，更不传 `session_id`。因此定时任务的每次触发都是无记忆的独立运行，无法表达「持续性任务记住上次上下文」的需求。

已实现的基础设施完备：
- `schedule_store.scheduled_tasks` 表（标准库 sqlite3，行 21-36 建表）已有 `id/name/cron_expr/timezone/user_id/agent_name/message/enabled/source/created_at`，`SELECT *` + `dict(row)` 返回任务字典；缺一个 `session_id` 列。
- `session_mgr` 提供 `load(session_id)`（文件不存在返回空列表）、`save(session_id, messages, user_id, agent_name)`（原子写 `.json.tmp → rename`，顺带刷新元数据索引并触发 TTL/容量维护）、`session_lock(session_id)`（per-session `asyncio.Lock`，同一 session 串行）。session_id 含 `/` 时自动建子目录。
- `session.md`「session_id 格式」表已为定时任务约定格式：`cron/{task_id}` 或调用方指定。

`session.md`（行 83-88）与 `scheduling.md`（行 449 待决问题已标 `[x]`）均已给出绑定语义方向，本 change 把它从「文档结论」落成「spec + 接线」。

约束（CLAUDE.md）：无 AI 框架；无 ORM（标准库 sqlite3 直接写 SQL）；无全局可变状态（`schedule_store.DB_PATH`、`cron_scheduler._CRON_YAML_PATH`、`session_mgr.SESSIONS_DIR` 均可 monkeypatch）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock `agent_loop.run`、隔离 SQLite 与 sessions 到 tmp_path；不吞异常。

## Goals / Non-Goals

**Goals:**
- 钉死定时任务触发时的 session 绑定语义：**可配置的「固定复用」与「每次独立」两态**，显式声明、不隐式推断，并给出**默认**结论。
- `scheduled_tasks` 表增可选 `session_id` 列并在 store/yaml 加载链路承载。
- `_fire` 据 `session_id` 解析出本次使用的 session_id，在 per-session 锁下接 `session_mgr.load`/`save`，把历史拼进本次 `agent_loop.run` 的输入、把结果写回。
- 独立语义下每次触发的 session **互不可见**（不复用、不串）。

**Non-Goals:**
- 不实现任务 CRUD 的对话工具/CLI 对 `session_id` 的编辑入口（属 scheduling v1.0 的 `edit_task`/`schedule_task` 扩展，本 change 只在 store 层与 yaml 承载该字段）。
- 不实现一次性/间隔任务类型、重试/兜底/幂等/执行日志（scheduling v1.0 其余项）。
- 不实现 session TTL/容量清理（已由 `session_mgr.maybe_run_maintenance` 实现，独立 session 自然被回收）。
- 不改 `agent_loop.run` 签名（它已接收 `messages`，本 change 只决定传入的 messages 与是否回写）。
- 不引入新依赖（仅用标准库 `uuid`/`asyncio`）。

## Decisions

### D1：绑定语义——可配置两态，默认「每次独立 session」

`scheduled_tasks` 增可选列 `session_id`：

- **`session_id` 非 NULL（固定复用语义）**：每次触发都用这个**固定** session_id。触发前 `session_mgr.load(sid)` 取到上次累积的历史，本次 `user` 消息拼在历史之后传给 `agent_loop.run`，完成后 `save(sid, ...)` 写回。跨触发上下文持续累积。适合「每日报告」「周报汇总」等需要连续记忆的任务。
- **`session_id` 为 NULL（独立语义，默认）**：每次触发**派生一个唯一的、本次专属的** session_id（`cron/{task_id}/{run_uuid}`，`run_uuid` 用 `uuid.uuid4()`）。`load` 必然返回空列表（新文件），本次只带 `user` 消息运行，`save` 写到本次专属文件。历次触发的 session 互不可见。

**为何默认「每次独立」**：
1. **与现状行为最接近**：当前 `_fire` 无记忆，默认独立语义不改变既有任务的可观察行为（仍是「每次从零开始」），升级零意外。
2. **安全默认**：跨触发累积上下文会让 session 无限增长、并可能把上一次的敏感输出泄漏进下一次——这应是用户**显式**选择的代价，而非默认承担。
3. **符合「显式声明不隐式推断」原则**：持续记忆是强语义，必须由配置 `session_id` 显式开启。

**Alternatives**：
- ①默认就复用 `cron/{task_id}`（固定）——被否：违背「显式声明」原则，且让所有现存任务一升级就开始累积上下文，行为突变且有泄漏风险。
- ②引入第三态「按 user_id/日期等 key 自动派生 session」——被否：属隐式推断，session.md 明确「不做隐式推断」；需要的话用户可把 `session_id` 配成含变量的固定值，但本 change 不内建该推断。
- ③独立语义复用同一个 `cron/{task_id}` 但每次 load 前清空——被否：清空=有损操作，且与「固定复用」实现互相纠缠；用 `run_uuid` 派生新文件更干净，且天然被 TTL/容量清理回收。

### D2：独立语义的 session_id 派生与不可见性

独立语义下 session_id = `cron/{task_id}/{run_uuid}`：
- 前缀 `cron/{task_id}` 与 session.md 约定一致，便于按任务归类、查询、清理。
- `run_uuid`（`uuid.uuid4().hex`）保证每次触发文件名唯一，历次互不可见。
- session_id 含 `/`，`session_mgr.save` 已会自动建子目录（`path.parent.mkdir(parents=True, exist_ok=True)`），无需额外处理。

**为何带 `run_uuid` 而非时间戳**：同一任务在极端情况下可能并发/补偿触发到同一秒，UUID 无碰撞风险；时间戳可能撞名导致两次触发误共享一个文件，破坏「互不可见」。

**Trade-off**：独立 session 会产生大量小文件——由已实现的 `session_mgr` TTL（`session_ttl_days`）与容量上限（`max_count`/`max_total_bytes`，LRU 清理）自然回收，本 change 不另建清理。

### D3：`_fire` 在 per-session 锁下 load → run → save

`_fire` 改为：
1. 解析 `sid = task["session_id"] or f"cron/{task['id']}/{uuid.uuid4().hex}"`。
2. `async with session_mgr.session_lock(sid):`
   - `history = await session_mgr.load(sid)`
   - `messages = [*history, {"role": "user", "content": task["message"]}]`
   - `reply = await agent_loop.run(messages, user_id=task["user_id"], agent_name=task.get("agent_name"))`
   - 把 user 消息与 assistant 回复追加进 `messages`，`await session_mgr.save(sid, messages, user_id=task["user_id"], agent_name=task.get("agent_name"))`

**为何在锁内**：固定语义下，同一固定 session 若被某任务高频触发或与其他来源（IM/HTTP 用同一 session_id）并发，需 per-session 串行避免历史互相覆盖——这正是 `session_mgr.session_lock` 的职责。独立语义下锁的 session_id 每次不同，等价无竞争、开销可忽略，统一走锁路径让代码单一。

**为何 save 传 `user_id`/`agent_name`**：复用 session_mgr 既有签名，顺带刷新 `session-metadata-index` 的元数据（最后活跃时间、message_count、归属），让定时任务产生的 session 也能被运维查询统计。

**Alternatives**：
- 固定语义下不回写、只读历史——被否：那样「累积上下文」无从谈起，必须 save 才能跨触发累积。
- 独立语义下完全不 load/不 save（沿用现状不接 session）——被否：会让两态走两条代码路径，且独立 session 不落盘则无法被运维查看本次对话；统一 load/save 让代码单一、可观测。

### D4：`scheduled_tasks` 增列与向后兼容

建表语句加 `session_id TEXT`（可空，无默认值即 NULL）；`create` 增 `session_id: str | None = None` 入参写入；`list_tasks` 的 `SELECT *` 自动带出。旧库升级由 `db-migration` 能力走 `ALTER TABLE ... ADD COLUMN session_id TEXT`（新列可空，旧行自动为 NULL = 独立语义，行为与现状一致）。

**为何可空且默认 NULL**：NULL 直接编码「独立语义（默认）」，无需额外标志位；旧任务零迁移成本即获得与现状一致的行为。

## Risks / Trade-offs

- [固定 session 跨触发无限增长 token/磁盘] → 由 `context_mgr` 的 in-session 压缩控制 token、`session_mgr` 的 TTL/容量清理控制磁盘；固定语义是用户显式选择，文档说明其代价。
- [固定 session 与 IM/HTTP 共用同一 session_id 时并发写冲突] → 统一在 `session_mgr.session_lock(sid)` 下串行，复用既有 per-session 锁；spec 加 scenario 覆盖同 session 串行。
- [独立语义产生大量小 session 文件] → 文件名带 `cron/{task_id}/` 前缀便于归类，由既有 TTL/容量清理回收；本 change 不另建清理。
- [旧库缺 `session_id` 列导致 `create` 报错] → 建表语句已含新列，新库直接可用；旧库由 `db-migration` 的 `ADD COLUMN` 补齐（可空，幂等）。
- [误以为本 change 提供了任务 session_id 的编辑入口] → proposal/design 明确：本 change 只在 store/yaml 层承载 `session_id`，对话工具/CLI 编辑入口属 scheduling v1.0 的 `edit_task`，不在本 change 范围。

## Open Questions

- 固定语义任务是否需要在 admin CLI 暴露「查看/重置某任务累积的 session」入口，便于运维清空跑偏的上下文？（倾向：复用 im-gateway 的 `/new` 清空机制或 session 管理 CLI，本 change 不内建。）
- 独立语义的 `cron/{task_id}/{run_uuid}` 前缀是否要让 `session-metadata-index` 支持按 `task_id` 前缀聚合查询「某任务的全部历史触发 session」？（本 change 仅保证前缀格式，聚合查询另议。）
- 当 `agent_loop.run` 触发期间抛异常时，本次 user 消息是否仍应 save 到固定 session（保留「问过什么」）还是整体回滚？（倾向：失败不 save 半截上下文，避免污染后续触发；与 scheduling v1.0 的失败重试/执行日志一并定，本 change 默认失败不回写。）
