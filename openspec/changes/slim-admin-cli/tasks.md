## 前置条件

**本 change 必须在 `add-platform-admin-apis` 完整落地 main 后执行。**

---

## 1. `admin_cli/main.py` 支持外部 argv

- [ ] 1.1 [测试] `tests/unit/test_admin_cli_main.py` 新增 `test_main_accepts_argv_param`：调用 `main(argv=["--help"])` 验证可接受外部 argv 而非只读 `sys.argv` → 运行必须红
- [ ] 1.2 [实现] 修改 `src/fleetent/platform/admin_cli/main.py` 的 `main()` 接受 `argv: list[str] | None = None` 参数；`None` 时 fallback 到 `sys.argv[1:]`
- [ ] 1.3 [验证] 运行 `uv run pytest tests/unit/test_admin_cli_main.py::test_main_accepts_argv_param -x -q` → 绿

## 2. `__main__.py` 新增 `admin` 与 `node` 子命令

- [ ] 2.1 [测试] `tests/unit/test_main_subcommands.py` 新增：
  - `test_admin_subcommand_dispatches`：`argv=["admin", "--help"]` 时调用 admin_cli
  - `test_node_start_subcommand_dispatches`：`argv=["node", "start"]` 时调用 node supervisor
  - `test_agent_run_does_not_import_platform`：调用 `argv=["agent", "run", "x"]` 后 `fleetent.platform.admin_cli` 不在 `sys.modules` → 运行必须红
- [ ] 2.2 [实现] `src/fleetent/__main__.py` 新增 `admin` 分支（懒加载 `platform.admin_cli.main`，转发 `argv[1:]`）和 `node start` 分支（懒加载 `node.app.main`）
- [ ] 2.3 [验证] 运行 `uv run pytest tests/unit/test_main_subcommands.py -x -q` → 全绿

## 3. 删除 B 类冗余 CLI 命令

- [ ] 3.1 [测试] `tests/unit/test_admin_cli_commands.py` 新增 `test_b_class_commands_removed`：构建 admin argparse，断言以下命令不在 subparsers 中：`create-user`、`list-users`、`rotate-key`、`block-user`、`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`、`observability`、以及 `kb connectors list/check/status/sync` → 运行必须红
- [ ] 3.2 [实现] 从以下模块的 `register()` 和 `handle()` 中移除 B 类命令：
  - `admin_cli/users.py`：移除 `create-user`、`list-users`、`rotate-key`、`block-user`
  - `admin_cli/agents.py`：移除 `update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`
  - `admin_cli/kb_connectors.py`：移除 `kb connectors list/check/status/sync`（保留 `extract-entities`）
  - `admin_cli/main.py`：从 `_COMMAND_MODULES` 移除 `observability` 模块
- [ ] 3.3 [验证] 运行 `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → 绿

## 4. Deprecation shim

- [ ] 4.1 [测试] `tests/unit/test_shims.py` 新增：
  - `test_fleetent_admin_shim_prints_deprecation`：调用 shim，捕获 stderr 含 `deprecated`
  - `test_fleetent_node_shim_prints_deprecation`：同上
- [ ] 4.2 [实现] 新建 `src/fleetent/_shims.py`，实现 `fleetent_admin_shim()` 和 `fleetent_node_shim()`（打印 DeprecationWarning 后修改 `sys.argv` 调用 `__main__.main()`）
- [ ] 4.3 [实现] `pyproject.toml` 将 `fleetent-admin` 和 `fleetent-node` 脚本条目改为 `fleetent._shims:fleetent_admin_shim` 和 `fleetent._shims:fleetent_node_shim`；运行 `uv sync` 使新入口生效
- [ ] 4.4 [验证] 运行 `uv run pytest tests/unit/test_shims.py -x -q` → 绿
- [ ] 4.5 [验证] 手动运行 `fleetent-admin --help`，确认打印 deprecation 警告后显示 admin help

## 5. 清理 B 类命令的旧测试

- [ ] 5.1 [实现] 搜索并删除 `tests/` 中专门测试已删 B 类命令的测试用例（`test_create_user_cmd`、`test_list_users_cmd`、`test_rotate_key_cmd` 等）
- [ ] 5.2 [验证] 运行 `uv run pytest tests/unit/test_admin_cli_commands.py tests/unit/test_admin_cli_main.py -x -q` → 全绿

## 6. 收尾验证

- [ ] 6.1 [验证] 运行 `make test-pr` → 全绿（unit + layer boundaries + ruff）
- [ ] 6.2 [验证] 运行 `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 6.3 [验证] 运行 `make test-unit-ci` → unit 覆盖率不低于 76%
