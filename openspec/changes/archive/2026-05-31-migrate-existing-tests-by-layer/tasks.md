## 0. 前置确认

- [x] 0.1 确认 `test-suite-organization` 已完成并归档
- [x] 0.2 确认当前 change 以测试、CI 和测试文档迁移为主；仅对测试移动暴露的 `sub_agent` import-order bug 做最小运行时修复
- [x] 0.3 记录根目录现有 `tests/test_*.py` 清单，作为迁移基线
- [x] 0.4 运行 `uv run pytest -x -q`，确认迁移前测试基线为绿

## 1. Unit tests 迁移

- [x] 1.1 将单模块、mock 外部依赖的测试移动到 `tests/unit/`
- [x] 1.2 修正移动后 import / fixture / monkeypatch 路径
- [x] 1.3 运行 `uv run pytest tests/unit -x -q`，确认 unit 层通过

## 2. Integration tests 迁移

- [x] 2.1 将 SQLite、Alembic、FastAPI、IM gateway、agent loop、store、runtime 协作测试移动到 `tests/integration/`
- [x] 2.2 修正移动后 import / fixture / monkeypatch 路径
- [x] 2.3 运行 `uv run pytest tests/integration -x -q`，确认 integration 层通过

## 3. E2E / evaluation 分类确认

- [x] 3.1 检查剩余根目录测试是否存在真正 CLI / HTTP 服务 / 完整入口链路测试
- [x] 3.2 如存在，将其移动到 `tests/e2e/`；否则记录现有 e2e 维持不变
- [x] 3.3 检查剩余根目录测试是否存在效果评估测试
- [x] 3.4 如存在，将其移动到 `tests/evaluation/`；否则记录现有 evaluation 维持不变
- [x] 3.5 分别运行 `uv run pytest tests/e2e -x -q` 和 `uv run pytest tests/evaluation -x -q`

## 4. Pytest / CI / 文档收敛

- [x] 4.1 更新 `pytest.ini`，移除 `tests` 根目录作为长期 collection layer
- [x] 4.2 更新 Bitbucket CI，确认 PR/main 仍运行 `tests/unit` 和 `tests/integration`
- [x] 4.3 更新 `AGENTS.md`：说明历史迁移完成后不得向 `tests/` 根目录新增测试
- [x] 4.4 更新 `CLAUDE.md`：同步同一测试分层规则
- [x] 4.5 确认 `tests/` 根目录不再存在 `test_*.py`

## 5. 收尾验证

- [x] 5.1 运行 `uv run pytest tests/unit -x -q`
- [x] 5.2 运行 `uv run pytest tests/integration -x -q`
- [x] 5.3 运行 `uv run pytest -x -q`
- [x] 5.4 运行 `uv run ruff format src tests`
- [x] 5.5 运行 `uv run ruff check src tests`
- [x] 5.6 运行 `uv run mypy src`
- [x] 5.7 运行 `openspec validate migrate-existing-tests-by-layer`
