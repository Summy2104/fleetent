## Why

`session_mgr.py` 当前只存 session 的消息历史 JSON，**没有任何元数据索引**：无创建时间、最后活跃时间、消息数、关联 user_id 等。docs/capabilities/session.md 第 69 行明确标注「无创建时间、最后活跃时间等索引，无法按时间排序或统计」。

这导致运维与管理无从下手：无法回答「某 user 有哪些 session」「哪些 session 最久未活跃」「全系统 session 总数与消息量」等基本统计问题，也使后续的 TTL 清理、LRU 容量管理只能靠全盘扫描文件 mtime（成本高、信息少）。本 change 为每个 session 维护一份轻量元数据索引，落实 session.md 规划项「session 轻量元数据索引」（第 79-81 行），支持管理与统计查询。

## What Changes

- 在 `users.db` 新增 **`sessions` 表**（aiosqlite 直接建表，**禁止 ORM**），存储每个 session 的轻量元数据：`session_id`（主键）、`user_id`、`created_at`、`updated_at`（最后活跃时间）、`message_count`、`agent_name`。
- 新增 `session_index.py` 模块，提供元数据**写入/更新**与**查询**函数：
  - `record_activity(session_id, user_id, message_count, agent_name)`：upsert 元数据；首次写入 `created_at`，每次写入刷新 `updated_at`。
  - `get(session_id)`：返回单个 session 的元数据（不存在返回 None）。
  - `list_by_user(user_id)`：返回某 user 的全部 session 元数据，按 `updated_at` 倒序。
  - `count() / total_message_count()`：全系统统计。
- `session_mgr.save()` 完成持久化后**触发元数据更新**（在写入消息文件成功后调用 `session_index.record_activity`），保证元数据与消息文件一致。
- 元数据索引**与消息文件物理分离**——存于 `users.db`，不增加 session JSON 文件本身体积（对齐 session.md 第 81 行）。
- 元数据更新失败**不破坏消息持久化**：消息文件已原子写成功后再更新索引；索引更新异常被捕获并记日志，不让索引故障回滚已成功的消息写入。

## Capabilities

### New Capabilities
- `session-metadata-index`: 每个 session 的轻量元数据索引（创建时间、最后活跃时间、消息数、user_id、agent_name），存于 `users.db` 的 `sessions` 表（aiosqlite，无 ORM）；提供 upsert 写入与按 user / 全系统统计的查询；与消息文件物理分离、互不影响。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。session_mgr.save() 在原子写成功后追加一次索引更新副作用，消息持久化行为本身不变。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/session_index.py`（`DB_PATH` 常量可注入、建表 DDL、upsert 与查询函数；aiosqlite，无 ORM）。
  - 修改 `src/fleetent/session_mgr.py`：`save()` 在原子写成功后调用 `session_index.record_activity`（异常捕获，不回滚消息写入）。
- **数据**：`users.db` 新增 `sessions` 表（与 `users` / `im_users` / `agents` 等同库，见 CLAUDE.md 数据目录）。
- **配置**：无新 Settings 字段（仅复用 `DB_PATH`）。
- **测试**：新增 `tests/test_session_index.py`；monkeypatch `session_index.DB_PATH → tmp_path / "x.db"`（SQLite 隔离，对齐 CLAUDE.md 测试规范）；`session_mgr` 集成测试 monkeypatch `SESSIONS_DIR` 与 `session_index.DB_PATH`。
- **不影响**：`load()` / `session_lock()` 既有行为；原子写契约；不引入新依赖（aiosqlite 已是项目既有 SQLite 访问方式）。
