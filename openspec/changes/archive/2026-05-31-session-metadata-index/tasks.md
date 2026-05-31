## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `users.db` 既有表与 aiosqlite 访问模式（参照 `user_store.py` / `agent_store.py` 的 `DB_PATH` 注入、建表 DDL、`aiosqlite.connect` 直接写 SQL；禁止 ORM）
- [x] 1.2 核实 `session_mgr.save()` 现签名 `(session_id, messages)`（行 37）与原子写流程（行 38-42），确认新增可选参数 `user_id` / `agent_name` 向后兼容
- [x] 1.3 确认 SQLite 测试隔离方式：`monkeypatch session_index.DB_PATH → tmp_path / "x.db"`（CLAUDE.md 测试规范）

## 2. 建表与模块骨架（session_index.py）

- [x] 2.1 Write failing tests：导入 `session_index`、调用建表/初始化后，`sessions` 表存在且含 `session_id` / `user_id` / `created_at` / `updated_at` / `message_count` / `agent_name` 列。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：`session_index.py` 顶部 import → `DB_PATH` 可注入常量 → 建表 DDL（`CREATE TABLE IF NOT EXISTS sessions ...`，`session_id` 主键）+ `_ensure_table()`。看到绿

## 3. record_activity —— 首次插入

- [x] 3.1 Write failing tests（monkeypatch `DB_PATH → tmp_path`）：首次 `record_activity` 后 `get()` 返回该行，`created_at == updated_at`，`message_count` 正确。看到红
- [x] 3.2 Implement `record_activity()`（INSERT ... ON CONFLICT upsert）+ `get()` 查询。看到绿

## 4. record_activity —— upsert 更新语义

- [x] 4.1 Write failing tests：对同一 `session_id` 第二次 `record_activity`（更大 message_count、更晚时间）后，`created_at` 不变、`updated_at` 刷新、`message_count` 更新。看到红
- [x] 4.2 Implement：ON CONFLICT DO UPDATE 保留 `created_at`、刷新 `updated_at`、覆盖 `message_count` / `user_id` / `agent_name`。看到绿

## 5. 查询函数

- [x] 5.1 Write failing tests：`get()` 不存在返回 None；`list_by_user()` 返回该 user 全部 session 且按 `updated_at` 倒序。看到红
- [x] 5.2 Implement `list_by_user()`（`WHERE user_id = ? ORDER BY updated_at DESC`）。看到绿

## 6. 全系统统计

- [x] 6.1 Write failing tests：插入若干 session 后 `count()` 返回总数、`total_message_count()` 返回 message_count 之和。看到红
- [x] 6.2 Implement `count()` 与 `total_message_count()`（聚合 SQL）。看到绿

## 7. 接入 session_mgr.save()

- [x] 7.1 Write failing tests（monkeypatch `SESSIONS_DIR` 与 `session_index.DB_PATH`）：`save()` 成功后元数据被记录（message_count == len(messages)，含透传的 user_id / agent_name）。看到红
- [x] 7.2 Implement：`save()` 新增可选参数 `user_id=None` / `agent_name=None`；原子写成功后调用 `session_index.record_activity`。看到绿

## 8. 故障隔离

- [x] 8.1 Write failing tests：mock `session_index.record_activity` 抛异常，验证消息文件已写入不被回滚、`save()` 不向上抛异常、异常被记日志。看到红
- [x] 8.2 Implement：`save()` 中 `record_activity` 包裹 try/except，捕获后 `logger.warning` 不重抛。看到绿

## 9. 收尾

- [x] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）确认无回归
- [x] 9.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误模式
- [x] 9.3 复核 `load()` / `session_lock()` 既有行为与原子写契约未受影响（既有测试仍绿）
