## 1. 输入 schema 净化（TDD）

- [x] 1.1 Write failing unit tests for `_sanitize_input_schema`（+ `_defs_rename` 助手）：缺 `type`/`properties` → 补 `type:"object"`+`properties:{}`；`definitions` + `#/definitions/Foo` → `$defs` + `#/$defs/Foo`；已合规（`$defs`+type:object）schema 语义不变；非 dict 入参 → 安全默认；嵌套 definitions 递归处理；异常输入不抛。运行 `uv run pytest -x -q` 看红。
- [x] 1.2 Implement `_sanitize_input_schema` 与递归 `_defs_rename`，并在 `_register_tool_http`/`_register_tool_stdio` 注册前应用；使 1.1 全绿。

## 2. 协议版本协商 + 能力捕获（TDD）

- [x] 2.1 Write failing unit tests：`McpServerConfig` 含 `protocol_version`/`capabilities` 字段；`_open_session`（mock `client.post` 返回带 `protocolVersion`/`capabilities` 的 init result）捕获到 server 状态；`_base_headers` 在 `protocol_version` 置位时含 `MCP-Protocol-Version`、未置位时不含；服务端缺 `protocolVersion` 时回退客户端版本；缺 `capabilities` 时为空 dict。运行 `uv run pytest -x -q` 看红。
- [x] 2.2 Implement：`McpServerConfig` 加 `protocol_version`/`capabilities` 运行时字段；`_open_session`（http）与 `_register_stdio_server`（stdio，`session.initialize()` 返回值）捕获版本/能力；`_base_headers` 回发 `MCP-Protocol-Version`；使 2.1 全绿。

## 3. tools/list 游标分页（TDD）

- [x] 3.1 Write failing unit tests：`_list_all_tools_http`（mock `_post_jsonrpc` 返回两页含/不含 `nextCursor`）跨页聚合、命中 `_MAX_TOOL_PAGES` 上限即停；单页只发一次；`_register_http_server` 注册多页工具；`_list_all_tools_stdio`（fake session 分页返回）聚合。运行 `uv run pytest -x -q` 看红。
- [x] 3.2 Implement `_list_all_tools_http`/`_list_all_tools_stdio` + 页数上限，改造 `_register_http_server`/`_probe_http_tools`/`_register_stdio_server`/`_probe_stdio_tools`；使 3.1 全绿。

## 4. 文档与收尾

- [x] 4.1 更新 `docs/capabilities/mcp.md`（分页/schema 净化/协议版本头/能力捕获并入现状）；`docs/records/mcp-enhancement-2026-06/decision-log.md` 追加 Change 2 节（问题/决策/改进/送审点）。
- [x] 4.2 收尾全量校验：`env -u FLEETENT_HOME make test-unit-ci`（unit + 75% coverage）、对改动文件跑 ruff/mypy、`uv run python scripts/check_test_layers.py` 全部通过。
