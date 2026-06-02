## 0. 前置确认

- [ ] 0.1 确认本 change 只拆 admin CLI 文件结构，不改命令语义
- [ ] 0.2 确认 `fleetent-admin = "fleetent.admin:main"` 暂时不改
- [ ] 0.3 确认 `fleetent.admin` 只保留 shim / entrypoint，不承载业务逻辑
- [ ] 0.4 确认不引入 Click / Typer 或其他 CLI framework

## 1. Package entrypoint and shim

- [ ] 1.1 Write failing tests: `fleetent.platform.admin_cli.main.main` 可 import
- [ ] 1.2 Write failing tests: `fleetent.admin.main` 与新 package entrypoint 行为等价
- [ ] 1.3 Implement: 新增 `platform/admin_cli` package skeleton，保留 `fleetent.admin` shim
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/integration/test_admin.py -x -q`

## 2. Split user / IM / agent / schedule commands

- [ ] 2.1 Write failing tests: create/list/rotate user CLI 行为保持不变
- [ ] 2.2 Write failing tests: IM pending/approve/block CLI 行为保持不变
- [ ] 2.3 Write failing tests: channel assignment 和 default agent CLI 行为保持不变
- [ ] 2.4 Write failing tests: schedule list/add/remove CLI 行为保持不变
- [ ] 2.5 Implement: 拆出 `users.py`、`im.py`、`agents.py`、`schedules.py`
- [ ] 2.6 Verify green: 运行 `uv run pytest tests/integration/test_admin.py -x -q`

## 3. Split Pilot operations commands

- [ ] 3.1 Write failing tests: `kb connectors list/check/status/sync` CLI 行为保持不变
- [ ] 3.2 Write failing tests: `diagnostics export/retention` CLI 行为保持不变
- [ ] 3.3 Write failing tests: `observability traces/usage/performance` CLI 行为保持不变
- [ ] 3.4 Implement: 拆出 `kb_connectors.py`、`diagnostics.py`、`observability.py`
- [ ] 3.5 Verify green: 运行 `uv run pytest tests/integration/test_admin.py -x -q`

## 4. Common helpers and cleanup

- [ ] 4.1 Write failing tests: CLI 输出仍然脱敏，不暴露 token / secret / payload 原值
- [ ] 4.2 Implement: 共享 helper 移入 `common.py`
- [ ] 4.3 Implement: 确保 `src/fleetent/admin.py` 不保留业务逻辑
- [ ] 4.4 Verify green: 运行 `uv run pytest tests/integration/test_admin.py -q`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/architecture/source-module-organization-roadmap.md`，标记 admin CLI split 已有 implementation spec
- [ ] 5.2 更新 OpenSpec `module-boundaries` 或 deployment 相关说明
- [ ] 5.3 运行 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [ ] 5.4 运行 `uv run ruff format src tests`
- [ ] 5.5 运行 `uv run ruff check src tests`
- [ ] 5.6 运行 `uv run mypy src`
- [ ] 5.7 运行 `uv run pytest -x -q`
- [ ] 5.8 运行 `openspec validate 2026-06-02-admin-cli-module-split --strict`
- [ ] 5.9 运行 `git diff --check`
