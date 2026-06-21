## 1. 删 admin_cli 空模块

- [x] 1.1 [测试] `tests/unit/test_admin_cli_commands.py`（或新建）加 `test_command_modules_has_no_empty_module`：断言 `admin_cli.main._COMMAND_MODULES` 不含 `im`、`agents` → 红
- [x] 1.2 [实现] `admin_cli/main.py`：从 import 与 `_COMMAND_MODULES` 移除 `im`、`agents`；删除文件 `admin_cli/im.py`、`admin_cli/agents.py`
- [x] 1.3 [验证] `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → 绿；`fleetent admin --help` 仍正常列出保留命令

## 2. 删 deprecation shim（BREAKING）

- [x] 2.1 [测试] 改 `tests/unit/test_admin_entrypoint_cleanup.py`：把"`fleetent-admin` 指向 shim"断言改为断言 `pyproject scripts` **不含** `fleetent-admin` 与 `fleetent-node`；保留 legacy `fleetent.admin` 不可导入断言 → 红
- [x] 2.2 [实现] `pyproject.toml`：从 `[project.scripts]` 删除 `fleetent-admin`、`fleetent-node` 两行；删除 `src/fleetent/_shims.py`；删除 `tests/unit/test_shims.py`
- [x] 2.3 [实现] `uv sync` 使入口变更生效
- [x] 2.4 [验证] `uv run pytest tests/unit/test_admin_entrypoint_cleanup.py -x -q` → 绿

## 3. 同步其余下游测试

- [x] 3.1 [实现] `tests/integration/test_deployment_docs.py`：核对/更新与 `fleetent-admin`/`fleetent-node` 相关断言，使其与"入口已移除、文档用 `fleetent admin`"一致
- [x] 3.2 [验证] `uv run pytest tests/integration/test_deployment_docs.py -x -q` → 绿

## 4. agent runtime 启动不加载 admin（守护新 spec）

- [x] 4.1 [测试] 确认/补 `test_agent_run_does_not_import_platform`（同进程：sys.modules.pop + monkeypatch agent_app.serve）仍绿 → 守护 spec「agent run 不加载 admin 代码」
- [x] 4.2 [验证] `uv run pytest -k "import_platform or admin_subcommand" tests/unit -q` → 绿

## 5. 收尾验证

- [x] 5.1 [验证] `git grep -n "fleetent-admin\|fleetent-node" -- ':!openspec/changes'` → 除文档迁移提示外无功能性残留（pyproject/_shims 已清；测试仅保留负向断言）
- [x] 5.2 [验证] `make test-pr` → 全绿
- [x] 5.3 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [x] 5.4 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [x] 5.5 [验证] `openspec validate remove-legacy-admin-entrypoints`；archive 后 `opsx:verify` 确认 agent-runtime-cli / module-boundaries / install-bootstrap specs 与实现一致
