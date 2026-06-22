## 1. 守门测试（验证删除目标，先写先红）

- [x] 1.1 [测试] `tests/unit/test_server_lifespan_and_wiring.py` 新增 `test_server_does_not_import_run_stream`：读取 `server.py` 源码，断言不含 `run_stream` import → 运行必须红
- [x] 1.2 [测试] `tests/unit/test_server_lifespan_and_wiring.py` 新增 `test_no_playground_scheduler`：断言 lifespan 启动后 `chat_admin_api` 没有 `run_playground` 注入（仍为默认 stub）→ 运行必须红
- [x] 1.3 [验证] 运行 `uv run pytest tests/unit/test_server_lifespan_and_wiring.py::test_server_does_not_import_run_stream tests/unit/test_server_lifespan_and_wiring.py::test_no_playground_scheduler -x -q` → 确认红

## 2. server.py 清理

- [x] 2.1 [实现] 删除 `from fleetent.runtime import run_stream`（line 52）
- [x] 2.2 [实现] 删除 `_pg_run` 函数全体（含内部 lazy import `from fleetent.runtime.snapshot import _governance_from_file`，约 40 行）
- [x] 2.3 [实现] 删除 `chat_admin_api.run_playground = _pg_run` wiring
- [x] 2.4 [实现] 删除 `_run_playground_retention` 函数、`maint = AsyncIOScheduler()` 块（含 `maint.add_job` + `maint.start()`）
- [x] 2.5 [验证] 运行 `uv run pytest tests/unit/test_server_lifespan_and_wiring.py -x -q` → 确认 1.1 和 1.2 新增测试绿

## 3. chat_admin_api.py 清理

- [x] 3.1 [实现] 删除 7 条 `/admin/chat/*` 路由 handler：`playground_start`、`list_playground_sessions`、`delete_playground_session`、`playground_message`、`playground_message_stream`、`pin_playground_session`、`export_playground_session`
- [x] 3.2 [实现] 删除 seam 定义：`run_playground`、`run_playground_stream`、`purge_expired_playground`
- [x] 3.3 [实现] 删除 helper：`_require_own_playground`、`_require_agent`
- [x] 3.4 [验证] 运行 `uv run pytest tests/integration/test_chat_admin_api.py -x -q` → 确认 session 治理测试仍绿（`test_takeover_*`、`test_force_end_*`、`test_clear_*`、`test_bulk_*`、`test_session_*`、`test_reset_*`、`test_viewer_*`、`test_list_sessions_*`）

## 4. 测试清理（删旧 playground 测试）

- [x] 4.1 [实现] 删除 `tests/integration/test_chat_admin_api.py` 中 playground 专属测试：`test_playground_start_isolated`、`test_playground_message_passes_overrides`、`test_overrides_are_request_scoped`、`test_playground_message_rejects_non_playground`、`test_playground_bypass_audited`、`test_export_audited`、`test_export_markdown_format`、`test_purge_expired_playground_removes_unpinned`、`test_playground_stream_sse`、`test_chat_start_records_owner`、`test_chat_sessions_listed_per_user`、`test_chat_cross_user_access_denied`
- [x] 4.2 [实现] 删除 `tests/unit/test_server_lifespan_and_wiring.py` 中对 `playground_retention` scheduler 和 `run_playground` wiring 的旧断言
- [x] 4.3 [验证] 运行 `uv run pytest tests/integration/test_chat_admin_api.py tests/unit/test_server_lifespan_and_wiring.py -x -q` → 全绿

## 5. 收尾验证

- [x] 5.1 [验证] 运行 `make test-pr` → 全绿（含 unit + layer boundaries + ruff）
- [x] 5.2 [验证] 运行 `uv run pytest tests/integration -q` → 无新增失败
