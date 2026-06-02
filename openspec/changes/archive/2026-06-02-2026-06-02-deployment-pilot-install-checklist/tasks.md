# tasks

## 1. OpenSpec proposal

- [x] 创建 proposal、design、tasks 和 deployment spec delta
- [x] 运行 `openspec validate 2026-06-02-deployment-pilot-install-checklist --strict` 确认 proposal 有效

## 2. Checklist 文档

- [x] Write failing tests：新增 `tests/integration/test_deployment_docs.py`，断言 `docs/deployment/pilot-install-checklist.md` 存在并覆盖 Pilot MVP 必要章节、命令和 secret 边界
- [x] Verify red：运行 `uv run pytest tests/integration/test_deployment_docs.py -x -q`，确认因 checklist 不存在或内容缺失失败
- [x] Implement：新增 `docs/deployment/pilot-install-checklist.md`，并更新 `docs/capabilities/deployment.md` 与 `docs/capabilities/intelligence-roadmap.md`
- [x] Verify green：运行 `uv run pytest tests/integration/test_deployment_docs.py -x -q`，确认文档测试通过

## 3. 验证与归档

- [x] 运行相关分层测试：`uv run pytest tests/integration/test_deployment_docs.py -x -q`
- [x] 运行 `uv run ruff format src tests`
- [x] 运行 `uv run ruff check src tests`
- [x] 运行 `uv run mypy src`
- [x] 运行 `uv run pytest -x -q`
- [x] 运行 `openspec validate 2026-06-02-deployment-pilot-install-checklist --strict`
- [x] 运行 `git diff --check`
- [x] 所有 checkbox 完成后归档 change 并验证 `openspec/specs/deployment/spec.md`
