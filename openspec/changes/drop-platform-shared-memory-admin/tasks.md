## 1. 删共享记忆 HTTP API

- [ ] 1.1 [测试] `tests/integration/test_server_lifespan_and_wiring.py`(或等价)加/改 `test_no_shared_memory_admin_router`:断言 app 路由中不含 `/admin/memory/shared`,server 不 import `shared_memory_admin_api` → 红
- [ ] 1.2 [实现] 删 `src/fleetent/platform/shared_memory_management/` 整包;移除 `server.py` 第 48 行 import 与第 237 行 `include_router`
- [ ] 1.3 [实现] 删 `tests/integration/test_shared_memory_admin_api.py`
- [ ] 1.4 [验证] `uv run pytest tests/integration/test_server_lifespan_and_wiring.py -x -q` → 绿;`GET /admin/memory/shared` 返回 404

## 2. 删共享记忆 CLI

- [ ] 2.1 [测试] `tests/unit/test_admin_cli_commands.py` 加 `test_memory_shared_cli_removed`:断言 `memory` 命令不在 admin argparse、`shared_memory` 不在 `_COMMAND_MODULES` → 红
- [ ] 2.2 [实现] 从 `admin_cli/main.py` 的 import 与 `_COMMAND_MODULES` 移除 `shared_memory`;删 `admin_cli/shared_memory.py`
- [ ] 2.3 [实现] 删 `tests/integration/test_shared_memory_admin_cli.py`
- [ ] 2.4 [验证] `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → 绿;`fleetent admin --help` 不再列出 memory 命令

## 3. 文档与文档测试同步

- [ ] 3.1 [实现] `docs/roadmaps/intelligence-roadmap.md` 与 `intelligence-roadmap-test-manual.md`:移除 `memory shared` CLI 引用,改述为"经 reflection proposal/apply 生命周期"
- [ ] 3.2 [实现] `tests/integration/test_deployment_docs.py::test_intelligence_roadmap_manual_uses_current_shared_memory_cli`:改为不再断言 CLI 存在(断言文档不把已删 CLI 列为当前入口);或按文档现状重命名/调整
- [ ] 3.3 [验证] `uv run pytest tests/integration/test_deployment_docs.py -x -q` → 绿

## 4. 收尾验证

- [ ] 4.1 [验证] `make test-pr` → 全绿
- [ ] 4.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 4.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [ ] 4.4 [验证] `git grep -n "memory/shared\|memory shared\|shared_memory_management\|shared_memory_admin" -- src tests docs ':!openspec/changes'` → 无遗漏功能性引用(memory.shared 数据层与 reflection 生命周期保留,不在此列)
- [ ] 4.5 [验证] `openspec validate drop-platform-shared-memory-admin`;archive 后 `opsx:verify` 确认 shared-memory-admin-api 下线、manual-maintenance-entrypoints 与实现一致
- [ ] 4.6 [验证] 确认 `memory.shared` 数据层与 `apply_shared_memory_proposal`(reflection 生命周期)仍可用:`uv run pytest tests/unit/test_coverage_memory_and_platform_logic.py -x -q` → 绿
