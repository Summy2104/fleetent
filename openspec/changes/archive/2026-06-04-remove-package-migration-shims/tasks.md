## 1. 基线与回归测试（红→绿）

- [x] 1.1 记录基线门禁数字：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`、`uv run mypy src`、`get_schemas()`、`openspec validate --all --strict`
- [x] 1.2 写失败测试 `tests/unit/test_legacy_flatpath_import_cleanup.py`：parametrize 32 个旧模块路径断言 `ModuleNotFoundError` + 正向抽查 6 个新包路径——此时 shim 仍在，旧路径用例**必须红**
- [x] 1.3 删除 32 个 shim 文件（`git rm`）使旧路径用例转绿；运行 `uv run pytest tests/unit/test_legacy_flatpath_import_cleanup.py -q` 看绿

## 2. 文档与 spec 同步

- [x] 2.1 改 README.md「Adding Tools」示例：`# src/fleetent/tools.py`→`# src/fleetent/tools/builtin_tools.py`，`from fleetent.tool_registry import tool`→`from fleetent.tools import tool`
- [x] 2.2 改 `openspec/specs/package-architecture/spec.md`：6 个能力域的「旧扁平路径仅为 shim」措辞与 Scenario 改为「已移除、不可导入」
- [x] 2.3 改 `openspec/specs/module-boundaries/spec.md`：为 runtime/model/tools/skills/session 域补齐「legacy 导入已移除」表述（spec delta 以 MODIFIED/ADDED 形式承载）

## 3. 门禁与收尾

- [x] 3.1 全量回归：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 0 failed；`get_schemas()`=12；`uv run mypy src` 不新增（≤32）
- [x] 3.2 关键自检：旧路径 `fleetent.agent_loop` 等抛 `ModuleNotFoundError`，`import fleetent.runtime, fleetent.tools` + `get_schemas()` 正常
- [x] 3.3 `ruff format`/`ruff check` 只动本次改动文件；`openspec validate --all --strict` 全过
