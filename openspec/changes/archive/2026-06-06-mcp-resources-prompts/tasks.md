## 1. 合成工具构件：参数/JSON化/分派（TDD）

- [x] 1.1 Write failing unit tests：`_utility_params`（read_resource→`{uri}`、get_prompt→`{name, arguments}`、list_*→`{}`）；`_jsonify`（dict→JSON、pydantic-like(model_dump)→JSON）；`_call_utility` http（mock `_post_jsonrpc` 返回 `{"result": ...}` → 返回 result 的 JSON）；`_call_utility` stdio（fake session 的 list_resources/read_resource → JSON）；unavailable server 短路返回 unavailable 文本。运行 `uv run pytest -x -q` 看红。
- [x] 1.2 Implement `_UTILITY_TOOL_SPECS`、`_utility_params`、`_jsonify`、`_call_http_utility`、`_call_stdio_utility`、`_call_utility`，使 1.1 全绿。

## 2. 门控注册 + 接线 + 刷新保留（TDD）

- [x] 2.1 Write failing unit tests：`_register_utility_tools`（caps 含 resources → 注册 `{id}__list_resources`/`__read_resource`；含 prompts → `__list_prompts`/`__get_prompt`；都不含 → 无；scope!=None → 无）；刷新保留——`_reregister_stdio_tools` 后合成工具仍在（server.capabilities 含 resources）。运行 `uv run pytest -x -q` 看红。
- [x] 2.2 Implement `_register_utility_tools`/`_register_utility_tool`；在 `_register_http_server`/`_register_stdio_server`/`_reregister_stdio_tools` 末尾调用之，使 2.1 全绿。

## 3. 文档与收尾

- [x] 3.1 更新 `docs/capabilities/mcp.md`（resources/prompts 合成工具并入现状、移出规划中）；`docs/records/mcp-enhancement-2026-06/decision-log.md` 追加 Change 6 节，并补一段「程序总结」（6 变更全部完成）。
- [x] 3.2 收尾全量校验：`env -u FLEETENT_HOME make test-unit-ci`、对改动文件 ruff/mypy、`uv run python scripts/check_test_layers.py` 全部通过。
