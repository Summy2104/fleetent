## Context

`session_mgr.py`（共 43 行）只持久化 session 的消息历史 JSON（`save()` 行 37-42），不记录任何元数据。docs/capabilities/session.md 第 69 行：「无创建时间、最后活跃时间等索引，无法按时间排序或统计」；第 79-81 行规划「session 轻量元数据索引」，并明确「存于 `users.db` 的 `sessions` 表，不增加 session 文件本身体积」。

`users.db` 是 SQLite 主库（CLAUDE.md 数据目录），既有 `users` / `im_users` / `agents` / `traces` / `memory_items` 等表，访问方式统一为 stdlib sqlite3 直接写 SQL（CLAUDE.md Forbidden Patterns：禁止 ORM）。本 change 在同库新增 `sessions` 表。

本 change 与 `session-ttl-cleanup`、`session-disk-management` 互补但独立：TTL/LRU 当前各自用文件 mtime 做判定，本元数据索引为它们提供更丰富、可查询的依据（后续可由它们改用索引替代全盘扫描），但本 change 不修改那两者。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（用 stdlib sqlite3 直接写 SQL）；禁止全局可变状态（`DB_PATH` 必须可 monkeypatch 注入）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；SQLite 测试隔离 `monkeypatch DB_PATH → tmp_path`。

## Goals / Non-Goals

**Goals:**
- 为每个 session 维护轻量元数据：`session_id` / `user_id` / `created_at` / `updated_at` / `message_count` / `agent_name`。
- 存于 `users.db` 的新表 `sessions`，与消息文件物理分离。
- 提供 upsert 写入（`record_activity`）与查询（按 session、按 user、全系统统计）。
- `session_mgr.save()` 成功后触发元数据更新，二者最终一致。
- 索引故障不破坏消息持久化。

**Non-Goals:**
- 不实现 TTL 清理（`session-ttl-cleanup` 范围）与 LRU 容量管理（`session-disk-management` 范围）；本 change 只提供它们可选用的数据。
- 不引入精确 token 统计（`message_count` 为消息条数，token 估算非本次必需，留作后续可选字段）。
- 不暴露 HTTP/CLI 管理端点（查询函数先就位，端点接入为后续 change）。
- 不改动 `load()` / `session_lock()` 与原子写契约。

## Decisions

### D1：用 stdlib sqlite3 在 users.db 建 sessions 表，禁止 ORM
新增 `src/fleetent/session_index.py`：
- `DB_PATH = Path("data/users.db")`（模块级可注入常量，对齐其它 store 模块）。
- 建表 DDL（`CREATE TABLE IF NOT EXISTS sessions (...)`）：`session_id TEXT PRIMARY KEY` / `user_id TEXT` / `created_at REAL` / `updated_at REAL` / `message_count INTEGER` / `agent_name TEXT`。`created_at` / `updated_at` 用 epoch 秒（`time.time()`）。
- 所有读写经 `sqlite3.connect(DB_PATH)` 直接写 SQL。

**为何**：CLAUDE.md 明令禁止 ORM、统一用 stdlib sqlite3；session.md 第 81 行指定存于 `users.db` 的 `sessions` 表。SQLite 索引天然支持按 user / 时间排序与聚合统计，优于 JSON 索引文件。
**Alternatives**：①轻量 JSON 索引文件（单文件存全部元数据）——被否，并发写需自己加锁、统计需全量加载、与 session.md「存于 users.db」明确冲突；②复用 traces 表——被否，语义不同（traces 是 append-only 运行日志，session 元数据是 per-session 可变 upsert）。

### D2：upsert 语义与 created_at / updated_at
`record_activity(session_id, user_id, message_count, agent_name)` 用 `INSERT ... ON CONFLICT(session_id) DO UPDATE`：
- 首次插入：`created_at = updated_at = now`。
- 冲突更新：保留原 `created_at`，刷新 `updated_at = now`、覆盖 `message_count` / `user_id` / `agent_name`。

**为何**：`created_at` 应固定为首次时间、`updated_at` 反映最后活跃，二者语义不同；ON CONFLICT upsert 是 SQLite 原生原子操作，无需先查后写的竞态。
**Alternatives**：先 SELECT 再决定 INSERT/UPDATE——被否，两步非原子、并发下有竞态。

### D3：save() 在原子写成功后触发索引更新，故障隔离
`session_mgr.save()` 流程改为：原子写消息文件（现状行 37-42）成功后，调用 `session_index.record_activity(...)`（`message_count = len(messages)`）。该调用包裹 try/except，异常时 `logger.warning` 后吞掉，**不影响已成功的消息写入**。
**为何**：消息持久化是主路径、必须可靠；元数据索引是辅助、可容忍短暂不一致（下次 save 会补正）。CLAUDE.md「不吞异常，catch 后必须 log」——此处 catch 后 log.warning 合规。`record_activity` 需要 `user_id` / `agent_name`：由调用方（agent_loop）经 `save()` 透传；为向后兼容，`save()` 新增可选参数 `user_id=None` / `agent_name=None`，缺省时元数据相应字段为 NULL。
**为何（参数）**：`save()` 现签名仅 `(session_id, messages)`；新增可选参数向后兼容，既有调用不传也能工作（元数据降级为部分信息）。
**Alternatives**：①索引更新失败回滚消息写入——被否，本末倒置，辅助索引不应阻断主数据；②save 内重新读取文件计数——被否，已持有 `messages`，直接 `len()` 即可。

### D4：查询函数集合
- `get(session_id) -> dict | None`：单 session 元数据。
- `list_by_user(user_id) -> list[dict]`：按 `updated_at DESC` 排序（最近活跃在前）。
- `count() -> int` / `total_message_count() -> int`：全系统聚合。

**为何**：覆盖 session.md「支持管理和统计」的核心查询；按 `updated_at` 倒序天然服务「最久未活跃」类运维问题。
**Alternatives**：暂不提供聚合统计——被否，session.md 第 79 行明确「支持管理和统计」，count/total 是统计的最小集。

## Risks / Trade-offs

- [索引与消息文件不一致（save 成功但索引更新失败）] → D3 保证消息为准、索引可容忍短暂滞后；下次同 session 的 save 会 upsert 补正；不一致仅影响统计精度，不影响对话功能。
- [既有 save() 调用方未传 user_id / agent_name 导致元数据不全] → 新增参数为可选、向后兼容；元数据相应字段 NULL 不影响按 session_id 的查询；agent_loop 接入透传后逐步补全。
- [sessions 表与 users.db 其它表共库的写竞争] → stdlib sqlite3 默认 WAL/串行写足以应对 session 级低频写；与既有 store 模块同库同模式，无新增风险。
- [message_count 仅为条数、非 token 量] → session.md 提及「总 token 估算」为可选增强；本次先落 message_count，token 估算作为后续可加字段，schema 预留扩展空间（新增列即可）。

## Open Questions

- 是否需要 `token_estimate` 列——session.md 第 80 行提及但非统计必需；本次先不加，后续若 LRU/计费需要再以 `ALTER TABLE ADD COLUMN` 扩展。
- 管理查询的对外暴露形式（HTTP / CLI）——本 change 先就位查询函数，端点接入留待后续 change。
