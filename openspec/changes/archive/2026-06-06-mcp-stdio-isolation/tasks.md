## 1. 受控环境构建（TDD）

- [x] 1.1 Write failing unit tests for `_safe_base_env` 与 `_subprocess_env`：白名单变量（如 `PATH`）存在时被纳入；非白名单的宿主密钥（monkeypatch 注入 `os.environ`）不出现在结果；`_subprocess_env(server)` = 白名单 + `server.env`；`server.env` 同名键覆盖白名单值；空 `server.env` 时仅返回白名单。运行 `uv run pytest -x -q` 看红。
- [x] 1.2 Implement `_SAFE_ENV_KEYS_*` 常量、`_safe_base_env()`、`_subprocess_env(server)`，使 1.1 全绿。

## 2. register / probe 接线（TDD）

- [x] 2.1 Write failing unit tests：`_register_stdio_server` 与 `_probe_stdio_tools` 构建 `StdioServerParameters` 时传入的 env 不含 monkeypatch 注入的宿主密钥、含 `PATH`、含 server 显式 env（通过 monkeypatch `mcp.client.stdio.StdioServerParameters` 捕获 env 后短路）。运行 `uv run pytest -x -q` 看红。
- [x] 2.2 改造 `_register_stdio_server` 与 `_probe_stdio_tools`：env 由 `{**os.environ, **server.env} if server.env else None` 改为 `_subprocess_env(server)`，使 2.1 全绿。

## 3. 文档与收尾

- [x] 3.1 更新 `docs/capabilities/mcp.md`（stdio 子进程环境隔离并入现状、移出规划中）；`docs/records/mcp-enhancement-2026-06/decision-log.md` 追加 Change 3 节。
- [x] 3.2 收尾全量校验：`env -u FLEETENT_HOME make test-unit-ci`、对改动文件 ruff/mypy、`uv run python scripts/check_test_layers.py` 全部通过。
