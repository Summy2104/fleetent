## 0. 前置确认

- [x] 0.1 确认本 change 不修改运行时代码
- [x] 0.2 确认本 change 只做测试目录/命令/CI/agent 指南规范
- [x] 0.3 确认不一次性迁移所有测试文件

## 1. 测试目录与 pytest 配置

- [x] 1.1 新建 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/evaluation/`
- [x] 1.2 更新 `pytest.ini`，显式收集分层测试目录
- [x] 1.3 保留根目录 tests 兼容期说明，后续新增测试不得继续放在 `tests/` 根目录
- [x] 1.4 运行 `uv run pytest -x -q`，确认现有测试仍可收集并通过

## 2. 代表性测试迁移

- [x] 2.1 将 `tests/smoke/smoke.py` 迁移为 `tests/e2e/test_smoke.py`
- [x] 2.2 将 migration / trace / usage / observability logging 测试迁移到 `tests/integration/`
- [x] 2.3 更新被迁移测试的 import / fixture 路径
- [x] 2.4 运行对应分层测试命令，确认迁移后通过

## 3. 命令与 CI

- [x] 3.1 更新 Makefile：新增 `test-unit`、`test-integration`、`test-e2e`、`test-evaluation`
- [x] 3.2 更新 Bitbucket CI：PR/main 默认运行 unit 和 integration，e2e/evaluation 不默认运行
- [x] 3.3 保留 `make test` / `uv run pytest` 作为完整测试入口
- [x] 3.4 运行 CI 等价命令，确认通过

## 4. Agent / Claude 指南

- [x] 4.1 更新 `AGENTS.md`：说明四类测试目录、适用场景和默认命令
- [x] 4.2 更新 `CLAUDE.md`：同步同一测试分层规范
- [x] 4.3 明确 TDD 红绿循环默认跑最近相关分层测试，收尾跑 `uv run pytest -x -q`

## 5. 收尾验证

- [x] 5.1 运行 `uv run pytest -x -q`
- [x] 5.2 运行 `uv run ruff format src tests`
- [x] 5.3 运行 `uv run ruff check src tests`
- [x] 5.4 运行 `uv run mypy src`
- [x] 5.5 运行 `openspec validate test-suite-organization`
