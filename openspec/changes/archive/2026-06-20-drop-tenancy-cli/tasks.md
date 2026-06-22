## 1. 删租户 CLI

- [x] 1.1 [测试] `tests/integration/test_tenancy_admin.py`（或 `tests/unit/test_admin_cli_commands.py`）加 `test_tenancy_cli_commands_removed`：断言 `create-tenant`/`list-tenants`/`create-team`/`set-user-tenant`/`set-approver` 不在 admin argparse subparsers，且 `tenancy` 不在 `_COMMAND_MODULES` → 红
- [x] 1.2 [实现] `admin_cli/main.py`：从 import 与 `_COMMAND_MODULES` 移除 `tenancy`；删除文件 `admin_cli/tenancy.py`
- [x] 1.3 [验证] `uv run pytest <上述测试> -x -q` → 绿；`fleetent admin --help` 不再列出租户命令、其余命令正常

## 2. 清理 CLI 测试，保留 HTTP 测试

- [x] 2.1 [实现] `tests/integration/test_tenancy_admin.py`：删除 `*_cli` 测试函数（test_create_tenant_cli / test_create_tenant_cli_generates_uuid_without_id / test_create_team_cli / test_list_tenants_cli / test_set_user_tenant_cli / test_set_tenant_approver_cli / test_set_team_approver_cli）及其专用 helper；保留全部 `test_api_*` HTTP 测试
- [x] 2.2 [验证] `uv run pytest tests/integration/test_tenancy_admin.py -x -q` → 绿（HTTP 测试全过）

## 3. 边界原则守门测试

- [x] 3.1 [测试] `tests/unit/` 加 `test_no_tenancy_direct_db_cli`：构建 admin argparse，断言租户业务命令均不存在（守护 module-boundaries 新 requirement）→ 红（删 CLI 前）→ 删后绿
- [x] 3.2 [验证] `uv run pytest tests/unit/test_no_tenancy_direct_db_cli.py -x -q` → 绿

## 4. 收尾验证

- [x] 4.1 [验证] `make test-pr` → 全绿
- [x] 4.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [x] 4.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [x] 4.4 [验证] `git grep -n "create-tenant\|create-team\|set-approver\|set-user-tenant\|list-tenants" -- src tests docs ':!openspec/changes'` → 无遗漏功能性引用
- [x] 4.5 [验证] `openspec validate drop-tenancy-cli --strict`；archive 后分别验证 `module-boundaries` 与 `tenancy-entities` spec，确认与实现一致
