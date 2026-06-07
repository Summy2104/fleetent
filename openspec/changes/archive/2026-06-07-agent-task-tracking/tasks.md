## 1. session 持久化 helper（TDD）

> 测试层：纯文件 I/O（`monkeypatch SESSIONS_DIR → tmp_path`）属「可注入文件边界」，放 `tests/unit`（对齐既有 `test_session_resume_marker.py`）。`cleanup_expired` 触及 SQLite index 用 `@patch("fleetent.session.index.delete_batch")`（对齐既有 `test_session_cleanup_index_sync.py`）。

- [x] 1.1 写失败测试（`tests/unit/test_session_todo_store.py`，`monkeypatch SESSIONS_DIR`）：`write_todo`/`read_todo`/`clear_todo` 往返、原子写（无半写态）、文件不存在→空列表、内容损坏→空列表 + warn、`clear_todo` 幂等、含 `/` 的 session_id 落子目录。运行 `uv run pytest tests/unit -x -q` 看红
- [x] 1.2 实现 `session/manager.py`：`_todo_path(session_id)`、`read_todo`、`write_todo`（原子 `tmp→replace`、**不取 `session_lock`**）、`clear_todo`（unlink suppress）；导出到 `session/__init__.py`。看绿
- [x] 1.3 写失败测试（`tests/unit`，`@patch fleetent.session.index.delete_batch` + `monkeypatch SESSIONS_DIR`）：`cleanup_expired()` 删过期主文件时连带删 `{sid}.todo`（存在则删、删除失败静默、不影响整批）。看红
- [x] 1.4 实现：`cleanup_expired` 的兄弟文件删除块加入 `{session_id}.todo`（仿 `.resume`/`.pre-compact.json`，best-effort suppress）。看绿

## 2. todo 工具升级（TDD）

> 测试层：`tests/unit/test_interaction_tools.py`（更新既有 todo 测试 + 新增，`monkeypatch SESSIONS_DIR` 隔离文件）。

- [x] 2.1 写失败测试（更新 `test_interaction_tools.py`）：`set` 替换并赋唯一 id + `pending`；`update` 按 id 改 status；已有 `in_progress` 时再置另一条为 `in_progress` 被拒绝且列表不变；`get` 渲染含 id/文本/状态；`clear` 清空并删 `{sid}.todo`；session 隔离；经 `set` 后同 `session_id` 重新读取（清进程内态/直接经 `read_todo`）仍得列表（持久化）；无 `session_id` 降级为临时列表（不写文件、不报错）；schema 仍含 `items`、新增 `action` 枚举与 `item_id`/`status`。看红
- [x] 2.2 实现：重写 `tools/interaction_tools.py` 的 `todo`（action `set`/`update`/`get`/`clear`、条目 `{id,text,status}` 状态机、单 `in_progress` 不变式、经 `session_mgr` helper lock-free 持久化、无 session_id 降级）；删除模块级 `_todo_store`。看绿

## 3. 死锁回归 + 收尾

- [x] 3.1 写回归测试（`tests/unit`，`monkeypatch SESSIONS_DIR`）：在持有 `session_lock(session_id)` 的上下文中调用 `todo`/`write_todo`（其持久化路径）不死锁（`asyncio.wait_for` 超时断言）。lock-free 实现下应绿；若红说明误取锁，修实现至绿
- [x] 3.2 收尾全绿：`uv run ruff format`（仅改动文件）、`uv run ruff check src tests`、`uv run mypy src`、`uv run python scripts/check_test_layers.py`、全量 `uv run pytest -x -q`
- [x] 3.3 `openspec validate agent-task-tracking --strict` 通过
