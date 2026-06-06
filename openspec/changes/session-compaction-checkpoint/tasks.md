## 1. Alembic migration：session_meta 表新增压缩记录列

- [x] 1.1 Write failing integration test: 在 tests/integration/ 验证 migration 054 执行后 sessions 表存在 last_compaction_at、messages_before_compaction、messages_after_compaction、compaction_summary_preview 四列，且现有行这四列值为 NULL
- [x] 1.2 Create migration 054_add_session_compaction_meta.py: ALTER TABLE sessions ADD COLUMN last_compaction_at REAL; ADD COLUMN messages_before_compaction INTEGER; ADD COLUMN messages_after_compaction INTEGER; ADD COLUMN compaction_summary_preview TEXT

## 2. session/manager.py：备份文件函数

- [x] 2.1 Write failing unit tests for write_compaction_checkpoint: 验证调用后 {session_id}.pre-compact.json 存在且内容正确；验证含 / 的 session_id 能正确写入子目录
- [x] 2.2 Implement write_compaction_checkpoint(session_id, messages): 原子写 tmp→rename，格式 {"messages": [...], "compacted_at": time.time()}；文件路径 SESSIONS_DIR / f"{session_id}.pre-compact.json"
- [x] 2.3 Write failing unit tests for delete_compaction_checkpoint: 验证存在时删除成功；验证不存在时不报错（幂等）
- [x] 2.4 Implement delete_compaction_checkpoint(session_id): suppress(FileNotFoundError) 静默处理
- [x] 2.5 Export write_compaction_checkpoint and delete_compaction_checkpoint via session/__init__.py

## 3. session_admin_store.py：update_compaction_meta

- [x] 3.1 Write failing integration test for update_compaction_meta: 验证调用后 sessions 表对应行的四列被正确更新；验证 summary_preview 被截断至 200 字符
- [x] 3.2 Implement update_compaction_meta(session_id, messages_before, messages_after, summary_preview, compacted_at): UPDATE sessions SET last_compaction_at=?, messages_before_compaction=?, messages_after_compaction=?, compaction_summary_preview=? WHERE session_id=?; summary_preview 截断至 200 字符

## 4. runtime/context.py：注入 checkpoint 调用

- [x] 4.1 Write failing unit tests for compaction checkpoint injection: patch session_mgr.write_compaction_checkpoint 和 session_admin_store.update_compaction_meta，调用 maybe_compress（有实际压缩发生时），验证两者均被调用且参数正确
- [x] 4.2 Inject write_compaction_checkpoint into maybe_compress: 在压缩执行前调用 session_mgr.write_compaction_checkpoint(session_id, messages)（仅当 session_id 非 None 且实际触发压缩时）；失败 best-effort（try/except，_logger.warn）
- [x] 4.3 Inject update_compaction_meta into maybe_compress: 压缩完成后调用 session_admin_store.update_compaction_meta(session_id, before, after, preview, time.time())；失败 best-effort
- [x] 4.4 Inject same checkpoint calls into compress_for_context_overflow: 同上模式（两处注入点：write_compaction_checkpoint 和 update_compaction_meta）

## 5. session/manager.py：cleanup_expired 跳过备份文件并同步删除

- [x] 5.1 Write failing unit tests for cleanup_expired pre-compact skip: 验证 cleanup_expired 不将 .pre-compact.json 文件纳入 TTL 过期判定（即有 .pre-compact.json 但无对应 .json 时，不尝试删除 .pre-compact.json 作为独立 session）
- [x] 5.2 Write failing unit tests for cleanup_expired pre-compact deletion: 验证 cleanup_expired 删除 session_id.json 后，同步删除对应的 session_id.pre-compact.json；验证备份不存在时不报错
- [x] 5.3 Update cleanup_expired to skip .pre-compact.json in rglob scan: 在 rglob 循环中加 path.name.endswith(".pre-compact.json") 跳过条件
- [x] 5.4 Update cleanup_expired to delete pre-compact file after main deletion: 删除 .json 成功后，with suppress(OSError): (SESSIONS_DIR / f"{session_id}.pre-compact.json").unlink()

## 6. 收尾验证

- [x] 6.1 Run full test suite: uv run pytest tests/unit tests/integration -x -q 验证全绿
- [x] 6.2 Run test layer check: uv run python scripts/check_test_layers.py
- [x] 6.3 Run lint and type check: uv run ruff format src tests && uv run ruff check src tests && uv run mypy src
