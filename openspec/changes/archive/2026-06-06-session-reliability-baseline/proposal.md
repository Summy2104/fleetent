## Why

Session 系统存在三个静默的可靠性缺陷：日志不落盘（structlog 遗漏）、文件清理后 SQLite 索引残留幽灵记录、管理接口无分页导致性能随数据量线性劣化。这三个问题均已通过对标 hermes-agent / claude-code / opencode 确认，属于当前最高性价比的修复。

## What Changes

- **session/manager.py 日志迁移**：删除 `import structlog`，换用 `get_logger("session.manager")`；所有 `logger.warning` → `_logger.warn`、`logger.info` → `_logger.info`，使 session 操作日志落盘并自动脱敏
- **session/index.py 新增删除接口**：增加 `delete(session_id)` 和 `delete_batch(session_ids)` 函数；`cleanup_expired()` 和 `enforce_capacity()` 在文件删除成功后调用 `delete_batch(removed)`，消除幽灵记录
- **list_by_user 游标分页**：`list_by_user(user_id, limit=50, before_updated_at=None)` 添加游标参数，基于 `updated_at` 降序 + LIMIT；`list_session_ids(prefix="", limit=None)` 添加可选 limit
- **session/__init__.py 公开 list_by_user**：将 `session_index.list_by_user` 通过 manager 层暴露为 `session_mgr.list_by_user`

## Capabilities

### New Capabilities

（无新独立能力，均为既有能力的修复与增强）

### Modified Capabilities

- `session-ttl-cleanup`：清理操作现在 SHALL 同步删除 SQLite `sessions` 表中对应行；现有 spec 仅要求删除文件，未规定 index 同步
- `session-disk-management`：容量淘汰操作现在 SHALL 同步删除 SQLite `sessions` 表中对应行
- `session-metadata-index`：新增删除接口（`delete` / `delete_batch`）；`list_by_user` 新增游标分页参数（`limit`、`before_updated_at`）
- `observability`：session 模块纳入自定义结构化日志覆盖范围

## Impact

- **修改文件**：`src/fleetent/session/manager.py`、`src/fleetent/session/index.py`、`src/fleetent/session/__init__.py`
- **测试**：`tests/unit/test_session_mgr.py`（现有）、`tests/integration/test_session_mgr.py`（现有）；新增 `tests/unit/test_session_logging.py`
- **无 schema 变更**：不涉及 Alembic migration，`sessions` 表结构不变
- **无破坏性变更**：`list_by_user` 新参数均有默认值，现有调用方不受影响
