## 前置条件

**本 change 必须在 `complete-admin-api-coverage` 完整落地 main 后执行。**（它补齐了 observability / service-principal / rotate-key / default-agent 四块 HTTP API，18 条命令才全部可安全删除。）apply 前先确认 main 已含这些端点。

---

## 1. `admin_cli/main.py` 参数化 + prog 修正

- [ ] 1.1 [测试] `tests/unit/test_admin_cli_main.py` 新增 `test_main_accepts_argv_param`（`main(argv=["--help"])` 可用）与 `test_help_prog_is_fleetent_admin`（默认 prog 为 `fleetent admin`）→ 红
- [ ] 1.2 [实现] `platform/admin_cli/main.py`：`main(argv: list[str] | None = None, prog: str = "fleetent admin")`，`None` 时 fallback `sys.argv[1:]`，`ArgumentParser(prog=prog)`，`parse_args(argv)`
- [ ] 1.3 [验证] `uv run pytest tests/unit/test_admin_cli_main.py -x -q` → 绿

## 2. `__main__.py` 接 admin / node 子命令

- [ ] 2.1 [测试] `tests/unit/test_main_subcommands.py` 新增 `test_admin_subcommand_dispatches`、`test_node_start_dispatches`、`test_node_without_start_errors`、`test_agent_run_does_not_import_platform`（同进程：先 `sys.modules.pop("fleetent.platform.admin_cli", None)` + monkeypatch `agent_app.serve`，调度后断言不在 sys.modules）→ 红
- [ ] 2.2 [实现] `__main__.py` 新增 `admin` 分支（懒加载 `platform.admin_cli.main`，调 `main(argv[1:], prog="fleetent admin")`）和 `node start` 分支（懒加载 `node.app.main`）；`node` 缺 `start` 报用法错误
- [ ] 2.3 [验证] `uv run pytest tests/unit/test_main_subcommands.py -x -q` → 全绿

## 3. 删 18 条冗余命令

- [ ] 3.1 [测试] `tests/unit/test_admin_cli_commands.py` 新增 `test_removed_commands_absent`：断言 18 条命令均不在 admin argparse subparsers → 红
- [ ] 3.2 [实现] 从各模块 `register()`/`handle()` 删除：
  - `users.py`：create-user、list-users、rotate-key、block-user
  - `agents.py`：update-agent、list-agent-versions、activate-agent-version、show-agent、assign-user、unassign-user、set-default-agent
  - `kb_connectors.py`：删 `connectors` 子命令树，保留 `extract-entities`
  - `main.py`：从 `_COMMAND_MODULES` 移除 `observability` 模块
- [ ] 3.3 [验证] `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → 绿

## 4. Deprecation shim（stderr）

- [ ] 4.1 [测试] `tests/unit/test_shims.py` 新增 `test_admin_shim_prints_to_stderr_and_rewrites_argv`、`test_node_shim_prints_to_stderr`（捕获 stderr 含迁移提示 + 断言 sys.argv 被改写 + `__main__.main` 被调）→ 红
- [ ] 4.2 [实现] 新建 `src/fleetent/_shims.py`：`fleetent_admin_shim()` / `fleetent_node_shim()` 用 `print(..., file=sys.stderr)`（**不用 `warnings.warn`**，DeprecationWarning 默认被过滤），改 `sys.argv` 后调 `__main__.main()`
- [ ] 4.3 [实现] `pyproject.toml`：`fleetent-admin` → `fleetent._shims:fleetent_admin_shim`，`fleetent-node` → `fleetent._shims:fleetent_node_shim`；`uv sync` 使生效
- [ ] 4.4 [验证] `uv run pytest tests/unit/test_shims.py -x -q` → 绿
- [ ] 4.5 [验证] 手动 `fleetent-admin --help`、`fleetent admin --help`，确认提示与 usage 正确

## 5. 同步下游引用（重头工作）

### 5a. 测试

- [ ] 5.1 [实现] `tests/unit/test_admin_entrypoint_cleanup.py`：把硬断言 `scripts["fleetent-admin"] == "fleetent.platform.admin_cli.main:main"` 改为指向 shim（否则 unit 必红）
- [ ] 5.2 [实现] 审计所有 `patch("sys.argv", ["fleetent-admin", ...])` 的 integration 测试（test_admin.py / test_tenancy_admin.py / test_node_admin_cli.py / test_shared_memory_admin_cli.py / test_admin_init_config.py 等），确认 `main()` 签名变更后兼容；删/改测被删命令的用例（含 `test_create_user_new_track.py`）
- [ ] 5.3 [实现] `tests/integration/test_deployment_docs.py`：移除对已删命令串（observability/kb connectors）的断言，与文档同步
- [ ] 5.4 [验证] `uv run pytest tests/unit -q` + 相关 integration 文件 → 无新增失败

### 5b. specs（本 change 已含 delta，apply 时随 archive 同步）

- [ ] 5.5 [验证] `openspec validate slim-admin-cli` 通过；archive 后 `opsx:verify` 确认 observability / knowledge-base / agent-definition / module-boundaries / agent-runtime-cli specs 与实现一致

### 5c. 文档

- [ ] 5.6 [实现] `README.md`、`AGENTS.md`：`fleetent-admin <cmd>` → `fleetent admin <cmd>`；被删命令处改指 HTTP API（**AGENTS.md 仅由本执行会话改，主会话勿并发编辑**）
- [ ] 5.7 [实现] `docs/operations/*`（runbook / acceptance / install-checklist）、`docs/capabilities/*`：被删命令的操作步骤改指 HTTP API，命名空间改 `fleetent admin`

### 5d. 脚本 / 构建

- [ ] 5.8 [实现] `Makefile` 的 `admin` target：`uv run fleetent-admin --help` → `uv run fleetent admin --help`
- [ ] 5.9 [实现] `scripts/install.sh` / `install-platform.sh` / `install-agent.sh`：`fleetent-admin seed-builtin-admin` 等改为 `fleetent admin seed-builtin-admin`，避免运维路径触发 deprecation

## 6. 收尾验证

- [ ] 6.1 [验证] `make test-pr` → 全绿（unit + layer boundaries + ruff）
- [ ] 6.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 6.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [ ] 6.4 [验证] `git grep -n "fleetent-admin\|fleetent-node" -- ':!openspec/changes/archive'` 复查无遗漏的功能性引用（shim 自身、迁移提示文案、archive 除外）
