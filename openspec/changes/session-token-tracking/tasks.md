## 1. Alembic migration 055：session_meta token 列

- [x] 1.1 Write failing integration test: 验证 migration 055 后 session_meta 表存在 total_input_tokens、total_output_tokens 两列，现有行为 0
- [x] 1.2 Create migration 055_add_session_token_columns.py: batch_alter_table session_meta add_column total_input_tokens INTEGER default 0, total_output_tokens INTEGER default 0

## 2. session_admin_store：add_token_usage + get_meta

- [x] 2.1 Write failing integration test for add_token_usage: 验证累加（两次 add(100,50) → 200/100）；验证首次自动创建行
- [x] 2.2 Implement add_token_usage(session_id, input_tokens, output_tokens): INSERT ... ON CONFLICT DO NOTHING 确保行存在，再 UPDATE SET total_input_tokens = COALESCE(total_input_tokens,0) + :in, total_output_tokens = COALESCE(...,0) + :out
- [x] 2.3 Write failing integration test for get_meta token fields: 验证 get_meta 返回值含 total_input_tokens、total_output_tokens
- [x] 2.4 Extend get_meta _COLS and row mapping to include token columns

## 3. session_mgr.save token_usage 参数

- [x] 3.1 Write failing unit test for save token_usage: patch session_admin_store.add_token_usage，验证 save(token_usage=(120,80)) 调用 add_token_usage(sid,120,80)；验证 token_usage=None 不调用；验证 add_token_usage 抛异常时 save 不抛出
- [x] 3.2 Add token_usage param to save: token_usage: tuple[int,int] | None = None；非 None 时 try add_token_usage best-effort（_logger.warn on failure）

## 4. 收尾验证

- [x] 4.1 Run full test suite: uv run pytest tests/unit tests/integration -x -q
- [x] 4.2 Run test layer check: uv run python scripts/check_test_layers.py
- [x] 4.3 Run lint: uv run ruff format src tests && uv run ruff check src tests
