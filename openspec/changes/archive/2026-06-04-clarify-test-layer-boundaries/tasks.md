## 0. 前置确认

- [x] 0.1 确认本 change 不修改生产行为，只处理测试文件归位、测试层规则和检查脚本
- [x] 0.2 记录当前 `tests/unit/` 违规基线：`TestClient`、`apply_migrations` / `command.upgrade`、
  `tests.integration.*` import、真实 DB runtime orchestration 命中文件
  - 2026-06-04 baseline: guard red 命中 `test_server_lifespan.py` 的 `TestClient` import / call、
    20 个直接使用 `tests.integration.*` / `apply_migrations` 的 unit 文件，以及
    3 个直接调用 `alembic.command.upgrade` 的 normalizer 文件。
- [x] 0.3 确认首批迁移清单；legacy SQLite store 例外若暂不迁移，写入 guard allowlist 并标注原因
  - 已迁移所有 guard 命中文件；本批无需 legacy SQLite allowlist。

## 1. Test-layer guard

- [x] 1.1 Write failing tests: 新增 `tests/unit/test_test_layer_guard.py`，构造临时 test tree，断言 guard 能
  检出 `tests/unit` 中的 `fastapi.testclient.TestClient` / `TestClient(`、`tests.integration.*`
  import、`apply_migrations`、`alembic.command.upgrade`，并报告文件、行号和原因；同时断言纯 unit
  fixture 不报错
- [x] 1.2 Implement: 新增 `scripts/check_test_layers.py`，使用 AST + 最小文本扫描实现 guard；默认扫描
  `tests/unit/`，支持传入自定义 root 以便单元测试使用，使 1.1 转绿
- [x] 1.3 Verify green: 运行 `uv run pytest tests/unit/test_test_layer_guard.py -x -q`

## 2. 高置信误放测试迁移

- [x] 2.1 Write failing tests: 运行 `uv run python scripts/check_test_layers.py`，确认当前 unit 目录存在
  guard violations（红）
- [x] 2.2 Implement: 将 `tests/unit/test_server_lifespan.py` 迁移 / 合并到 `tests/integration/`；更新重名
  integration 文件时保持测试语义不丢失
- [x] 2.3 Implement: 将直接使用 `tests.integration.test_migrations.apply_migrations` 或
  `alembic.command.upgrade` 的 high-confidence 文件迁移到 `tests/integration/`；必要时重命名避免和
  现有 integration 文件冲突
- [x] 2.4 Implement: 对暂不迁移的 legacy SQLite store 文件添加集中 allowlist，原因必须说明是短期
  legacy store boundary 例外，并在后续 task 中保留清理入口
- [x] 2.5 Verify green: 运行 `uv run python scripts/check_test_layers.py`，确认 guard 通过

## 3. 分层测试仍可运行

- [x] 3.1 Verify green: 运行 `uv run pytest tests/unit -x -q`，确认 unit 层收集和执行通过
- [x] 3.2 Verify green: 运行 `uv run pytest tests/integration -x -q`，确认迁移后的 integration 层通过
  - 2026-06-05: `1400 passed in 111.91s`.
- [x] 3.3 Verify green: 运行 `uv run pytest -x -q`，确认完整测试仍通过
  - 2026-06-05: `3107 passed, 14 skipped in 134.29s`.

## 4. 文档和 CI 辅助

- [x] 4.1 Write failing tests: 增加文档 / command contract 检查，断言 `AGENTS.md` 或项目指南中包含
  `scripts/check_test_layers.py` 和 unit 禁止规则
- [x] 4.2 Implement: 更新 `AGENTS.md` / `CLAUDE.md` 测试分层说明，明确 DB/Alembic/TestClient 属于
  integration，纯 tmp_path 文件边界可留 unit
- [x] 4.3 Implement: 在 Makefile 或项目脚本说明中加入 test-layer guard 命令；若接入 CI，作为
  unit/integration 前的快速检查
- [x] 4.4 Verify green: 运行文档 / command contract 测试

## 5. 收尾

- [x] 5.1 运行 `uv run ruff format src tests scripts`
  - 2026-06-05: `11 files reformatted, 461 files left unchanged`.
- [x] 5.2 运行 `uv run ruff check src tests scripts`
  - 2026-06-05: `All checks passed!`
- [x] 5.3 运行 `uv run mypy src`
  - 2026-06-05: `Success: no issues found in 194 source files`.
- [x] 5.4 运行 `uv run pytest -x -q`
  - 2026-06-05: `3107 passed, 14 skipped in 134.29s`.
- [x] 5.5 运行 `uv run python scripts/check_test_layers.py`
- [x] 5.6 运行 `openspec validate clarify-test-layer-boundaries --strict`
- [x] 5.7 运行 `git diff --check`
