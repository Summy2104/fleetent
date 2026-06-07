## 1. 检测 + 原地重注册（TDD）

- [x] 1.1 Write failing unit tests：`_is_tools_list_changed`（list_changed 消息→True；其他 method→False；无 root→False）；`_reregister_stdio_tools`（旧 t1/t2 → 新 t2/t3：t1 删、t2 留、t3 增；scope!=None 时不动共享注册表）。运行 `uv run pytest -x -q` 看红。
- [x] 1.2 Implement `_is_tools_list_changed` 与同步 `_reregister_stdio_tools`，使 1.1 全绿。

## 2. 刷新（identity guard + 去重）+ handler 接线（TDD）

- [x] 2.1 Write failing unit tests：`_refresh_stdio_tools`（注入 fake session 到 `_active_sessions`、fake `list_tools` 返回新列表 → 注册表更新；会话非当前 → identity guard 不动）；`_make_message_handler`：`await handler(list_changed_msg)` 后让出事件循环，注册表被刷新（全链路 handler→任务→刷新）。运行 `uv run pytest -x -q` 看红。
- [x] 2.2 Implement：`McpServerConfig` 加 `_list_refresh_lock`；`_refresh_stdio_tools`（identity guard + 锁去重 + 原地重注册）；`_make_message_handler`（检测→`create_task`）；`_register_stdio_server` 给 `ClientSession` 传 `message_handler=_make_message_handler(server, scope)`。使 2.1 全绿。

## 3. 文档与收尾

- [x] 3.1 更新 `docs/capabilities/mcp.md`（动态工具刷新并入现状、移出规划中，标注仅 stdio）；`decision-log.md` 追加 Change 5 节。
- [x] 3.2 收尾全量校验：`env -u FLEETENT_HOME make test-unit-ci`、对改动文件 ruff/mypy、`uv run python scripts/check_test_layers.py` 全部通过。
