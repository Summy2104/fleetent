# Tasks: kb-cleanup

> TDD Hard Gate：测试任务在实现任务之前；每步跑最窄命令，见红 → 见绿。删除类改动的"红"= 先把测试断言改为"新行为（命令/代码已不存在）"，此时旧代码仍在 → 见红；删完 → 见绿。

## 1. Retire platform `kb extract-entities` 命令

- [ ] 1.1 [test-red] 改 `tests/unit/test_admin_cli_commands.py`：把 `kb` 子命令期望改为**不存在**——将 `"set-default-agent"` 那组 `removed not in top_level` 循环加入 `"kb"`（或直接断言 `"kb" not in top_level`），删除 `kb_choices = ...` 及其后 `"connectors" not in kb_choices` / `"extract-entities" in kb_choices` 两行断言。跑 `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → **见红**（kb 仍注册）。
- [ ] 1.2 [impl] 删 `src/fleetent/platform/platform_cli/kb_connectors.py`；在 `src/fleetent/platform/platform_cli/main.py` 的 import 列表与 `_COMMAND_MODULES` 去除 `kb_connectors`。同步改 `tests/unit/test_coverage_cli_and_stats_handlers.py`：移除 `kb_connectors` import（第 9 行）与整个 `test_kb_connector_cli_only_keeps_extract_entities`（否则模块删除后该文件 import 崩）。跑 `uv run pytest tests/unit/test_admin_cli_commands.py tests/unit/test_coverage_cli_and_stats_handlers.py -x -q` → **见绿**。
- [ ] 1.3 grep 确认后端无残留：`grep -rn "extract-entities\|platform_cli.kb_connectors\|kb_connectors import" src tests`（`observability/diagnostics.py` 的 `list_kb_connectors` 是 KB connector 列表、与本命令无关，勿动）。

## 2. 删前端死 hook `useKbAgentsQuery`

- [ ] 2.1 [test] 改 `frontend/src/features/kb/api.test.tsx`：删除 `useKbAgentsQuery` 相关的 `renderHook` 用例（第 13、141 行附近的 import 与测试）。
- [ ] 2.2 [impl] 在 `frontend/src/features/kb/api.ts` 删除 `useKbAgentsQuery`（159-167 行）与 `KbAgentsResult` 类型（若仅此 hook 使用）；**保留 `kbAgentsKey`**（仍被其它 hook 的 `invalidateQueries` 引用，第 55/63/118 行）。跑 frontend 测试（`cd frontend && yarn test` 或项目约定命令）→ **绿**。
- [ ] 2.3 grep 确认无其它消费方：`grep -rn "useKbAgentsQuery\|KbAgentsResult" frontend/src`（应仅剩 0 处或保留的类型定义）。确认 `/admin/kb/{kb_id}/agents` 后端端点与 KB 详情 UI（用 `bound_agents`）未被触碰。

## 3. docstring 与文档

- [ ] 3.1 [impl] 给 `src/fleetent/knowledge_base/extract_cli.py` 缺 docstring 的私有辅助函数（`_wait_for_jobs`、`_parse_args`、`_require_known_kb`、`_print_summary`）补一行 Google 风格 docstring（只写"为什么/做什么"要点，勿冗余）。
- [ ] 3.2 [impl] 更新部署/运维文档：`grep -rn "platform kb extract-entities" docs` 找到引用处，改为引导使用 `fleetent kb-extract --config <kb-service.yaml> --kb <kb_id> [--wait]`（与 `deployment` spec delta 一致）。

## 4. 收尾门禁（全绿才算完）

- [ ] 4.1 全库 grep 零残留：`grep -rn "extract-entities" src tests docs` 仅剩测试中"不存在"守卫与 `deployment` spec；`grep -rn "platform_cli.kb_connectors" .` 为空。
- [ ] 4.2 `openspec validate kb-cleanup --strict`
- [ ] 4.3 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 4.4 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未新增跨包/反向依赖）
- [ ] 4.5 frontend lint + test 绿
- [ ] 4.6 tasks.md 全部 `[x]`；在功能分支 `openspec archive kb-cleanup`（同步 `deployment` spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
