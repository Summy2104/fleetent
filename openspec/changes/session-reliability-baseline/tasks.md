## 1. P0-1：session/manager.py 日志迁移

- [x] 1.1 Write failing tests for session.manager logging: 在 tests/unit/test_session_logging.py 中验证 cleanup_expired、enforce_capacity、maybe_run_maintenance 中 _logger 被正确调用（patch("fleetent.session.manager._logger")）
- [x] 1.2 Migrate session/manager.py to get_logger("session.manager"): 删除 import structlog，加 from fleetent.observability.structured_logging import get_logger，将 logger = structlog.get_logger(__name__) 替换为 _logger = get_logger("session.manager")，所有 logger.warning → _logger.warn，logger.info → _logger.info

## 2. P0-2：清理操作同步删除索引行

- [x] 2.1 Write failing tests for index delete: 在 tests/unit/test_session_mgr.py 中验证 delete(session_id) 删除指定行、delete_batch([]) 幂等、delete_batch([id1, id2]) 批量删除
- [x] 2.2 Add delete and delete_batch to session/index.py: 实现 delete(session_id: str) → None 和 delete_batch(session_ids: list[str]) → None，使用单事务批量 DELETE WHERE session_id IN (...)
- [x] 2.3 Write failing tests for cleanup_expired index sync: 验证 cleanup_expired() 删除文件后调用了 session_index.delete_batch(removed)（mock index.delete_batch）
- [x] 2.4 Wire delete_batch into cleanup_expired: 在 cleanup_expired() 末尾 try/except 中调用 session_index.delete_batch(removed)，异常记录 warn 不中断
- [x] 2.5 Write failing tests for enforce_capacity index sync: 验证 enforce_capacity() 淘汰文件后调用了 session_index.delete_batch(removed)
- [x] 2.6 Wire delete_batch into enforce_capacity: 同上模式，在 enforce_capacity() 末尾调用 session_index.delete_batch(removed)

## 3. P1-2：list_by_user 游标分页

- [x] 3.1 Write failing tests for paginated list_by_user: 验证 list_by_user(user_id, limit=2) 最多返回2条、list_by_user(user_id, before_updated_at=ts) 只返回 updated_at < ts 的记录、默认 limit=50
- [x] 3.2 Add limit and before_updated_at to list_by_user in session/index.py: 修改函数签名为 list_by_user(user_id: str, limit: int = 50, before_updated_at: float | None = None)，SQL 加 AND updated_at < ? 条件（可选）和 LIMIT ? 子句
- [x] 3.3 Write failing tests for list_session_ids limit: 验证 list_session_ids(limit=5) 最多返回5条、不传 limit 返回全量
- [x] 3.4 Add limit to list_session_ids in session/manager.py: 修改函数签名为 list_session_ids(prefix: str = "", limit: int | None = None)，在返回前应用 [:limit]（已是内存操作）
- [x] 3.5 Expose list_by_user via session/manager.py and __init__.py: 在 manager.py 添加 list_by_user 函数（委托给 session_index.list_by_user），在 __init__.py 添加导出

## 4. 收尾验证

- [x] 4.1 Run full test suite: uv run pytest tests/unit tests/integration -x -q 验证全绿
- [x] 4.2 Run test layer check: uv run python scripts/check_test_layers.py 确认无层次违规
- [x] 4.3 Run lint and type check: uv run ruff format src tests && uv run ruff check src tests && uv run mypy src
